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
        # Check ODOO_ENABLED flag explicitly
        settings = get_settings()
        if not settings.odoo_enabled:
            logger.info("⚠️  Odoo CRM disabled via ODOO_ENABLED=false")
            return False
        
        # Check credentials
        if not (self.server_url and self.username and self.password):
            logger.warning("⚠️  Odoo CRM credentials missing")
            return False
            
        return True

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
            logger.warning("⚠️  Odoo CRM not configured - sync skipped")
            return {
                "status": "pending",
                "crm_record_id": None,
                "error": "Odoo CRM not configured",
                "activity_id": None,
                "message": "Odoo credentials not provided",
            }

        try:
            logger.info(f"🔄 Starting Odoo sync for call: {call_reference}")
            
            # Search for existing lead/contact
            existing_record = await self._search_existing_record(
                phone=customer_phone,
                email=customer_email,
                call_reference=call_reference,
            )

            if existing_record:
                record_id = existing_record["id"]
                logger.info(f"✅ Found existing Odoo record: {record_id}")
            else:
                # Create new lead
                logger.info(f"📝 Creating new Odoo lead for: {call_reference}")
                record_id = await self._create_crm_record(
                    call_reference=call_reference,
                    customer_phone=customer_phone,
                    customer_email=customer_email,
                    customer_name=customer_name,
                    transcript=transcript,
                    analysis=analysis,
                )
                if not record_id:
                    logger.error("❌ Failed to create CRM record - record_id is None")
                    return {
                        "status": "failed",
                        "crm_record_id": None,
                        "error": "Failed to create CRM record",
                        "activity_id": None,
                        "message": "Could not create new lead in Odoo",
                    }
                logger.info(f"✅ Created new Odoo record: {record_id}")

            # Append analysis as note/activity
            activity_id = await self._create_activity(
                record_id=record_id,
                transcript=transcript,
                analysis=analysis,
                agent_name=agent_name,
            )
            logger.info(f"✅ Created activity: {activity_id}")

            # Create follow-up activity if escalation is medium or high
            followup_activity_id = None
            if analysis.escalation_risk in ["medium", "high"]:
                followup_activity_id = await self._create_followup_activity(
                    record_id=record_id,
                    escalation_risk=analysis.escalation_risk,
                    recommended_action=analysis.recommended_action,
                )
                logger.info(f"✅ Created follow-up activity: {followup_activity_id}")

            logger.info(f"✅ Odoo sync complete! Record ID: {record_id}")
            return {
                "status": "synced",
                "crm_record_id": record_id,
                "error": None,
                "activity_id": activity_id,
                "followup_activity_id": followup_activity_id,
                "message": f"Analysis synced to Odoo record {record_id}",
            }

        except Exception as e:
            logger.exception(f"❌ Odoo CRM sync failed: {str(e)}")
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
            # Get source ID - may be None, handle gracefully
            source_id = await self._get_or_create_source("AI Call Analysis")
            
            # Build record data, filtering out None values
            record_data = {
                "name": customer_name or call_reference or "Call Analysis Lead",
                "type": "lead",
            }
            
            # Only add optional fields if they have values
            if customer_phone:
                record_data["phone"] = customer_phone
            if customer_email:
                record_data["email_from"] = customer_email
            if source_id:
                record_data["source_id"] = source_id
                
            # Add description
            record_data["description"] = self._build_record_description(
                call_reference, transcript, analysis
            )

            logger.info(f"   📋 Record data: name={record_data['name']}, type={record_data['type']}")
            
            record_id = await self._odoo_rpc_call(
                "crm.lead",
                "create",
                [record_data],  # create() expects a list with dict
            )

            logger.info(f"   ✅ Created Odoo lead with ID: {record_id}")
            return record_id

        except Exception as e:
            logger.error(f"   ❌ Create CRM record failed: {str(e)}")
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

            activity_type_id = await self._get_or_create_activity_type("note")
            
            # Build activity data, filtering None values
            activity_data = {
                "res_model": "crm.lead",
                "res_id": record_id,
                "summary": activity_summary,
                "note": activity_description,
                "user_id": 2,  # Admin user
            }
            
            if activity_type_id:
                activity_data["activity_type_id"] = activity_type_id
            
            # date_deadline must be serializable - convert to string
            activity_data["date_deadline"] = datetime.utcnow().strftime("%Y-%m-%d")

            activity_id = await self._odoo_rpc_call(
                "mail.activity",
                "create",
                [activity_data],  # create() expects a list
            )

            logger.info(f"✅ Created Odoo activity: {activity_id}")
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
            activity_type_id = await self._get_or_create_activity_type("todo")
            due_date = datetime.utcnow() + timedelta(days=1 if escalation_risk == "medium" else 0)

            activity_data = {
                "res_model": "crm.lead",
                "res_id": record_id,
                "summary": f"Follow-up: {escalation_risk.upper()} Priority",
                "note": f"Escalation: {escalation_risk}\n\nRecommended Action:\n{recommended_action}",
                "user_id": 2,
                "date_deadline": due_date.strftime("%Y-%m-%d"),
            }
            
            if activity_type_id:
                activity_data["activity_type_id"] = activity_type_id

            activity_id = await self._odoo_rpc_call(
                "mail.activity",
                "create",
                [activity_data],  # create() expects a list
            )

            logger.info(f"✅ Created follow-up activity: {activity_id}")
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
                [[("name", "=", source_name)]],  # search expects [domain]
            )

            if result and isinstance(result, list) and len(result) > 0:
                return result[0]

            # Create new source
            source_id = await self._odoo_rpc_call(
                "crm.lead.source",
                "create",
                [{"name": source_name}],  # create expects [dict]
            )

            logger.info(f"✅ Created CRM source: {source_id}")
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
                [[("name", "=", activity_type)]],  # search expects [domain]
            )

            if result and isinstance(result, list) and len(result) > 0:
                return result[0]

            # Try to find default "To Do" type
            result = await self._odoo_rpc_call(
                "mail.activity.type",
                "search",
                [[("name", "=", "To Do")]],
            )

            if result and isinstance(result, list) and len(result) > 0:
                return result[0]
            
            # Return default activity type ID if search fails
            return 4

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
        """Make an XML-RPC call to Odoo using execute_kw method."""
        try:
            import xmlrpc.client
            
            common_url = f"{self.server_url}/xmlrpc/2/common"
            object_url = f"{self.server_url}/xmlrpc/2/object"

            logger.info(f"🔗 Odoo RPC Call: model={model}, method={method}")
            logger.info(f"   Server: {self.server_url}")
            logger.info(f"   DB: {self.db_name}, User: {self.username}")

            # Authenticate
            try:
                # Enable allow_none to handle None values in responses
                common = xmlrpc.client.ServerProxy(common_url, allow_none=True)
                uid = common.authenticate(self.db_name, self.username, self.password, {})
                logger.info(f"✅ Odoo authentication successful: UID={uid}")
            except Exception as auth_err:
                logger.error(f"❌ Odoo authentication failed: {auth_err}")
                raise Exception(f"Authentication failed: {str(auth_err)}")

            if not uid:
                raise Exception("Odoo authentication failed - no UID returned")

            # Execute RPC call using execute_kw (correct Odoo format)
            try:
                # Enable allow_none for responses
                models = xmlrpc.client.ServerProxy(object_url, allow_none=True)
                logger.info(f"   Calling: {model}.{method}(db={self.db_name}, uid={uid}, ...)")
                
                # For Odoo XML-RPC: execute_kw(db, uid, password, model, method, args, kwargs)
                # Filter out None values from kwargs to prevent marshaling errors
                clean_kwargs = {k: v for k, v in (kwargs or {}).items() if v is not None}
                
                # Clean args too - remove None values from lists
                clean_args = []
                for arg in args:
                    if isinstance(arg, dict):
                        # Remove None values from dict arguments
                        clean_args.append({k: v for k, v in arg.items() if v is not None})
                    else:
                        clean_args.append(arg)
                
                result = models.execute_kw(
                    self.db_name,
                    uid,
                    self.password,
                    model,
                    method,
                    clean_args,
                    clean_kwargs
                )
                logger.info(f"✅ Odoo RPC successful: result type={type(result).__name__}, result={result if not isinstance(result, list) else f'list[{len(result)}]'}")
                return result
            except Exception as call_err:
                logger.error(f"❌ Odoo RPC call failed: {call_err}")
                raise Exception(f"RPC call failed: {str(call_err)}")

        except Exception as e:
            logger.error(f"❌ Odoo RPC failed: {str(e)}")
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
