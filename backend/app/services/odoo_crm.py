"""Odoo CRM integration service for syncing call analysis results."""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import requests
from requests.auth import HTTPBasicAuth

from app.core.config import get_settings
from app.models.schemas import AnalysisResult

logger = logging.getLogger(__name__)


class OdooCRMClient:
    """Client for Odoo CRM integration via XML-RPC and REST APIs."""

    def __init__(self):
        settings = get_settings()
        self.server_url = settings.odoo_server_url
        self.db_name = settings.odoo_db_name
        self.username = settings.odoo_username
        self.password = settings.odoo_password
        self.api_key = settings.odoo_api_key
        self.enabled = bool(self.server_url and self.username and self.password)
        self.timeout = 15

    def is_configured(self) -> bool:
        """Check if Odoo is properly configured."""
        return self.enabled

    async def sync_analysis(
        self,
        call_reference: str,
        transcript: str,
        analysis: AnalysisResult,
        customer_phone: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_name: Optional[str] = None,
        agent_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Sync call analysis to Odoo CRM.
        
        Returns:
            {
                "status": "synced" | "pending" | "failed",
                "crm_record_id": int or None,
                "error": str or None,
                "activity_id": int or None,
                "message": str
            }
        """
        if not self.is_configured():
            return {
                "status": "pending",
                "crm_record_id": None,
                "error": "Odoo CRM not configured",
                "activity_id": None,
                "message": "Odoo credentials not provided",
            }

        try:
            # Search for existing lead/contact
            existing_record = await self._search_existing_record(
                phone=customer_phone,
                email=customer_email,
                call_reference=call_reference,
            )

            if existing_record:
                record_id = existing_record["id"]
                logger.info(f"Found existing Odoo record: {record_id}")
            else:
                # Create new lead
                record_id = await self._create_crm_record(
                    call_reference=call_reference,
                    customer_phone=customer_phone,
                    customer_email=customer_email,
                    customer_name=customer_name,
                    transcript=transcript,
                    analysis=analysis,
                )
                if not record_id:
                    return {
                        "status": "failed",
                        "crm_record_id": None,
                        "error": "Failed to create CRM record",
                        "activity_id": None,
                        "message": "Could not create new lead in Odoo",
                    }
                logger.info(f"Created new Odoo record: {record_id}")

            # Append analysis as note/activity
            activity_id = await self._create_activity(
                record_id=record_id,
                transcript=transcript,
                analysis=analysis,
                agent_name=agent_name,
            )

            # Create follow-up activity if escalation is medium or high
            followup_activity_id = None
            if analysis.escalation_risk in ["medium", "high"]:
                followup_activity_id = await self._create_followup_activity(
                    record_id=record_id,
                    escalation_risk=analysis.escalation_risk,
                    recommended_action=analysis.recommended_action,
                )

            return {
                "status": "synced",
                "crm_record_id": record_id,
                "error": None,
                "activity_id": activity_id,
                "followup_activity_id": followup_activity_id,
                "message": f"Analysis synced to Odoo record {record_id}",
            }

        except Exception as e:
            logger.exception("Odoo CRM sync failed")
            return {
                "status": "failed",
                "crm_record_id": None,
                "error": str(e),
                "activity_id": None,
                "message": f"CRM sync error: {str(e)}",
            }

    async def _search_existing_record(
        self,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        call_reference: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Search for existing lead/contact/opportunity in Odoo."""
        domain = []

        if phone:
            domain.append(("phone", "=", phone))
        elif email:
            domain.append(("email_from", "=", email))
        elif call_reference:
            domain.append(("name", "ilike", call_reference))
        else:
            return None

        try:
            # Try searching in crm.lead model
            result = await self._odoo_rpc_call(
                "crm.lead",
                "search_read",
                [domain],
                {"fields": ["id", "name", "phone", "email_from"]},
            )

            if result and len(result) > 0:
                return result[0]

            return None

        except Exception as e:
            logger.warning(f"Search existing record failed: {e}")
            return None

    async def _create_crm_record(
        self,
        call_reference: str,
        customer_phone: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_name: Optional[str] = None,
        transcript: str = "",
        analysis: Optional[AnalysisResult] = None,
    ) -> Optional[int]:
        """Create a new CRM lead record in Odoo."""
        try:
            record_data = {
                "name": customer_name or call_reference or "Call Analysis Lead",
                "phone": customer_phone or "",
                "email_from": customer_email or "",
                "description": self._build_record_description(
                    call_reference, transcript, analysis
                ),
                "source_id": await self._get_or_create_source("AI Call Analysis"),
                "type": "lead",
            }

            record_id = await self._odoo_rpc_call(
                "crm.lead",
                "create",
                record_data,
            )

            logger.info(f"Created Odoo lead: {record_id}")
            return record_id

        except Exception as e:
            logger.exception(f"Create CRM record failed: {e}")
            return None

    async def _create_activity(
        self,
        record_id: int,
        transcript: str = "",
        analysis: Optional[AnalysisResult] = None,
        agent_name: Optional[str] = None,
    ) -> Optional[int]:
        """Create an activity/note linked to the CRM record."""
        try:
            activity_summary = f"Call Analysis - {analysis.sentiment}" if analysis else "Call Analysis"
            activity_description = self._build_activity_description(
                transcript, analysis, agent_name
            )

            activity_data = {
                "res_model": "crm.lead",
                "res_id": record_id,
                "activity_type_id": await self._get_or_create_activity_type("note"),
                "summary": activity_summary,
                "note": activity_description,
                "user_id": 2,  # Admin user
                "date_deadline": datetime.utcnow().date(),
            }

            activity_id = await self._odoo_rpc_call(
                "mail.activity",
                "create",
                activity_data,
            )

            logger.info(f"Created Odoo activity: {activity_id}")
            return activity_id

        except Exception as e:
            logger.warning(f"Create activity failed: {e}")
            return None

    async def _create_followup_activity(
        self,
        record_id: int,
        escalation_risk: str = "medium",
        recommended_action: str = "",
    ) -> Optional[int]:
        """Create follow-up activity for escalated cases."""
        try:
            due_date = datetime.utcnow() + timedelta(days=1 if escalation_risk == "medium" else 0)

            activity_data = {
                "res_model": "crm.lead",
                "res_id": record_id,
                "activity_type_id": await self._get_or_create_activity_type("todo"),
                "summary": f"Follow-up: {escalation_risk.upper()} Priority",
                "note": f"Escalation: {escalation_risk}\n\nRecommended Action:\n{recommended_action}",
                "user_id": 2,
                "date_deadline": due_date.date(),
            }

            activity_id = await self._odoo_rpc_call(
                "mail.activity",
                "create",
                activity_data,
            )

            logger.info(f"Created follow-up activity: {activity_id}")
            return activity_id

        except Exception as e:
            logger.warning(f"Create follow-up activity failed: {e}")
            return None

    async def _get_or_create_source(self, source_name: str) -> Optional[int]:
        """Get or create a CRM source."""
        try:
            result = await self._odoo_rpc_call(
                "crm.lead.source",
                "search",
                [("name", "=", source_name)],
            )

            if result:
                return result[0]

            source_id = await self._odoo_rpc_call(
                "crm.lead.source",
                "create",
                {"name": source_name},
            )

            return source_id

        except Exception as e:
            logger.warning(f"Get or create source failed: {e}")
            return None

    async def _get_or_create_activity_type(self, activity_type: str) -> Optional[int]:
        """Get or create activity type (note, todo, call, etc)."""
        try:
            result = await self._odoo_rpc_call(
                "mail.activity.type",
                "search",
                [("name", "=", activity_type)],
            )

            if result:
                return result[0]

            # Use default activity type if not found
            result = await self._odoo_rpc_call(
                "mail.activity.type",
                "search",
                [("name", "=", "To Do")],
            )

            return result[0] if result else 4  # Default activity type ID

        except Exception as e:
            logger.warning(f"Get or create activity type failed: {e}")
            return 4

    async def _odoo_rpc_call(
        self,
        model: str,
        method: str,
        *args,
        **kwargs,
    ) -> Any:
        """Make an XML-RPC call to Odoo."""
        try:
            import xmlrpc.client
            from http.client import HTTPConnection, HTTPSConnection
            from socket import create_connection

            # Custom transport with timeout support
            class TimeoutHTTPSConnection(HTTPSConnection):
                def __init__(self, host, *args, timeout=None, **kwargs):
                    self.timeout = timeout
                    super().__init__(host, *args, **kwargs)

                def connect(self):
                    self.sock = create_connection((self.host, self.port), timeout=self.timeout)
                    if self._tunnel_host:
                        self._tunnel()
                    self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)

            class TimeoutHTTPConnection(HTTPConnection):
                def __init__(self, host, *args, timeout=None, **kwargs):
                    self.timeout = timeout
                    super().__init__(host, *args, **kwargs)

                def connect(self):
                    self.sock = create_connection((self.host, self.port), timeout=self.timeout)
                    if self._tunnel_host:
                        self._tunnel()

            class TimeoutTransport(xmlrpc.client.Transport):
                def __init__(self, timeout=None, *args, **kwargs):
                    self.timeout = timeout
                    super().__init__(*args, **kwargs)

                def make_connection(self, host):
                    if self._connection and host == self._connection[0]:
                        return self._connection[1]
                    if self.use_https:
                        conn = TimeoutHTTPSConnection(host, timeout=self.timeout)
                    else:
                        conn = TimeoutHTTPConnection(host, timeout=self.timeout)
                    self._connection = (host, conn)
                    return conn

            # Construct URLs
            if self.server_url.startswith("https://") and "/api/" not in self.server_url:
                rpc_url = f"{self.server_url}/xmlrpc/2/object"
            else:
                rpc_url = f"{self.server_url}/xmlrpc/2/object"

            common_url = f"{self.server_url}/xmlrpc/2/common"

            # Create proxies with custom transport
            transport = TimeoutTransport(timeout=self.timeout, use_https=True)
            common = xmlrpc.client.ServerProxy(common_url, transport=transport)
            uid = common.authenticate(self.db_name, self.username, self.password, {})

            if not uid:
                raise Exception("Odoo authentication failed")

            # Execute RPC call
            models = xmlrpc.client.ServerProxy(rpc_url, transport=transport)
            result = getattr(models, model).call(method, uid, self.password, *args, **kwargs)

            return result

        except Exception as e:
            logger.error(f"Odoo RPC call failed: {e}")
            raise

    def _build_record_description(
        self,
        call_reference: str,
        transcript: str,
        analysis: Optional[AnalysisResult] = None,
    ) -> str:
        """Build description for CRM record."""
        lines = [
            f"Call Reference: {call_reference}",
            f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Source: AI Call Analysis",
            "",
            "TRANSCRIPT:",
            transcript[:500] if transcript else "[No transcript]",
            "",
        ]

        if analysis:
            lines.extend([
                "ANALYSIS:",
                f"Sentiment: {analysis.sentiment}",
                f"Confidence: {analysis.confidence * 100:.0f}%",
                f"Issue Type: {analysis.issue_type}",
                f"Summary: {analysis.summary}",
                f"Escalation Risk: {analysis.escalation_risk}",
            ])

        return "\n".join(lines)

    def _build_activity_description(
        self,
        transcript: str,
        analysis: Optional[AnalysisResult] = None,
        agent_name: Optional[str] = None,
    ) -> str:
        """Build description for activity/note."""
        lines = []

        if agent_name:
            lines.append(f"Agent: {agent_name}")

        if analysis:
            lines.extend([
                f"Sentiment: {analysis.sentiment}",
                f"Confidence: {analysis.confidence * 100:.0f}%",
                f"Key Issues: {', '.join(analysis.key_issues) if analysis.key_issues else 'None'}",
                f"Recommended Action: {analysis.recommended_action}",
                f"Escalation Priority: {analysis.escalation_risk}",
                "",
                "TRANSCRIPT SUMMARY:",
                transcript[:300] if transcript else "[No transcript]",
            ])

        return "\n".join(lines)


async def sync_to_odoo(
    call_reference: str,
    transcript: str,
    analysis: AnalysisResult,
    customer_phone: Optional[str] = None,
    customer_email: Optional[str] = None,
    customer_name: Optional[str] = None,
    agent_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Sync call analysis to Odoo CRM (convenience function)."""
    client = OdooCRMClient()
    return await client.sync_analysis(
        call_reference=call_reference,
        transcript=transcript,
        analysis=analysis,
        customer_phone=customer_phone,
        customer_email=customer_email,
        customer_name=customer_name,
        agent_name=agent_name,
    )
