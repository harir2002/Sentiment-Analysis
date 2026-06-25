#!/usr/bin/env python
"""
Test script for Odoo CRM XML-RPC connection.

Usage:
  python test_odoo_connection.py

This script validates your Odoo credentials before running the full application.
"""
import xmlrpc.client as xmlrpc
from app.core.config import get_settings

def test_odoo_connection():
    """Test XML-RPC connection to Odoo."""
    settings = get_settings()
    
    if not settings.odoo_enabled:
        print("⚠️  Odoo CRM is not enabled (ODOO_ENABLED=false)")
        return True
    
    if not settings.odoo_server_url:
        print("❌ ODOO_SERVER_URL not configured")
        return False
    
    print(f"Testing Odoo connection...")
    print(f"  Server: {settings.odoo_server_url}")
    print(f"  Database: {settings.odoo_db_name}")
    print(f"  Username: {settings.odoo_username}")
    print()
    
    try:
        # Test common endpoint
        common_url = f"{settings.odoo_server_url}/xmlrpc/2/common"
        common = xmlrpc.ServerProxy(common_url, timeout=15)
        
        print("Authenticating...")
        uid = common.authenticate(
            settings.odoo_db_name,
            settings.odoo_username,
            settings.odoo_password,
            {}
        )
        
        if not uid:
            print("❌ Authentication failed - invalid credentials")
            return False
        
        print(f"✓ Authentication successful (UID: {uid})")
        print()
        
        # Test RPC endpoint
        object_url = f"{settings.odoo_server_url}/xmlrpc/2/object"
        models = xmlrpc.ServerProxy(object_url, timeout=15)
        
        print("Testing CRM models...")
        
        # Test search on crm.lead
        try:
            leads = models.call(
                "crm.lead",
                "search",
                uid,
                settings.odoo_password,
                [("name", "=", "TEST_CONNECTION_VERIFY")],
                {"limit": 1}
            )
            print(f"✓ crm.lead model accessible (found {len(leads)} test leads)")
        except Exception as e:
            print(f"❌ crm.lead model error: {e}")
            return False
        
        # Test mail.activity
        try:
            activities = models.call(
                "mail.activity",
                "search",
                uid,
                settings.odoo_password,
                [],
                {"limit": 1}
            )
            print(f"✓ mail.activity model accessible (total activities: {len(activities)})")
        except Exception as e:
            print(f"⚠️  mail.activity warning: {e}")
            # Not critical, might be missing in lite instances
        
        print()
        print("✅ Odoo connection test PASSED")
        print()
        print("Configuration is ready. You can enable ODOO_ENABLED=true to start syncing.")
        return True
        
    except Exception as e:
        print(f"❌ Connection test FAILED: {e}")
        print()
        print("Troubleshooting:")
        print("  1. Verify server URL is correct and accessible")
        print("  2. Check that XML-RPC is enabled in Odoo")
        print("  3. Confirm username and password are correct")
        print("  4. Verify database name matches your Odoo instance")
        print("  5. Check firewall allows outbound HTTPS to Odoo")
        return False


if __name__ == "__main__":
    success = test_odoo_connection()
    exit(0 if success else 1)
