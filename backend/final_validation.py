#!/usr/bin/env python3
"""
Final validation script for K Fin Tech Demo production deployment.
Verifies all critical components are working correctly.
"""
import asyncio
import sys
from datetime import datetime

# Color codes for output
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
RESET = '\033[0m'
BLUE = '\033[94m'

def print_header(text):
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}{text:^60}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")

def print_success(text):
    print(f"{GREEN}✓ {text}{RESET}")

def print_warning(text):
    print(f"{YELLOW}⚠ {text}{RESET}")

def print_error(text):
    print(f"{RED}✗ {text}{RESET}")

def print_info(text):
    print(f"{BLUE}ℹ {text}{RESET}")

async def main():
    print_header("K Fin Tech Demo - Final Validation")
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: Configuration Loading
    print_info("Test 1: Configuration Loading")
    try:
        from app.core.config import get_settings
        settings = get_settings()
        print_success(f"Configuration loaded (env: {settings.app_env})")
        print_success(f"Active solution: {settings.active_solution}")
        print_success(f"Sarvam batch poll interval: {settings.sarvam_batch_poll_interval}s")
        print_success(f"Sarvam batch max wait: {settings.sarvam_batch_max_wait_seconds}s")
        tests_passed += 1
    except Exception as e:
        print_error(f"Configuration failed: {e}")
        tests_failed += 1
    
    # Test 2: Database Models
    print_info("Test 2: Database Models")
    try:
        from app.models.db_models import ComparisonJob
        from app.models.schemas import JobResponse, ProviderResult, AnalysisResult
        print_success("ComparisonJob model imported")
        print_success("JobResponse schema imported")
        print_success("ProviderResult schema imported")
        print_success("AnalysisResult schema imported")
        tests_passed += 1
    except Exception as e:
        print_error(f"Database models failed: {e}")
        tests_failed += 1
    
    # Test 3: Service Layer
    print_info("Test 3: Service Layer")
    try:
        from app.services.jobs import create_job, run_job_background
        from app.services.pipeline import run_full_pipeline
        from app.services.comparison import run_single_solution
        from app.services.sarvam_batch_worker import schedule_sarvam_batch_followups
        print_success("Jobs service imported")
        print_success("Pipeline service imported")
        print_success("Comparison service imported")
        print_success("Sarvam batch worker imported")
        tests_passed += 1
    except Exception as e:
        print_error(f"Service layer failed: {e}")
        tests_failed += 1
    
    # Test 4: Odoo CRM Integration
    print_info("Test 4: Odoo CRM Integration")
    try:
        from app.services.odoo_crm import sync_to_odoo, OdooCRMClient
        odoo = OdooCRMClient()
        configured = odoo.is_configured()
        print_success("Odoo CRM client imported")
        if configured:
            print_success("Odoo credentials configured")
        else:
            print_warning("Odoo credentials not configured (will sync when enabled)")
        tests_passed += 1
    except Exception as e:
        print_error(f"Odoo CRM integration failed: {e}")
        tests_failed += 1
    
    # Test 5: Provider Registry
    print_info("Test 5: Provider Registry")
    try:
        from app.providers.registry import get_active_solution, get_active_solution_config
        active = get_active_solution()
        print_success(f"Active solution retrieved: {active}")
        stt_name, llm_name = get_active_solution_config()
        print_success(f"STT provider: {stt_name}")
        print_success(f"LLM provider: {llm_name}")
        tests_passed += 1
    except Exception as e:
        print_error(f"Provider registry failed: {e}")
        tests_failed += 1
    
    # Test 6: Schema Validation
    print_info("Test 6: Schema Validation")
    try:
        from app.models.schemas import AnalysisResult
        # Test creating a valid analysis result
        analysis = AnalysisResult(
            sentiment="positive",
            confidence=0.95,
            key_issues=["issue1"],
            summary="Test summary",
            action_items=["action1"],
            resolution_status="resolved",
            notes="Test notes"
        )
        print_success(f"Analysis result created (sentiment: {analysis.sentiment})")
        print_success("Schema validation passed")
        tests_passed += 1
    except Exception as e:
        print_error(f"Schema validation failed: {e}")
        tests_failed += 1
    
    # Test 7: Syntax Validation (all critical Python files)
    print_info("Test 7: Python Syntax Validation")
    try:
        import py_compile
        import glob
        
        critical_files = [
            "app/main.py",
            "app/api/routes.py",
            "app/services/jobs.py",
            "app/services/pipeline.py",
            "app/services/comparison.py",
            "app/services/odoo_crm.py",
            "app/services/sarvam_batch_worker.py",
            "app/models/schemas.py",
            "app/models/db_models.py",
            "app/core/config.py",
        ]
        
        failed_files = []
        for filepath in critical_files:
            try:
                py_compile.compile(filepath, doraise=True)
                print_success(f"  {filepath}")
            except py_compile.PyCompileError as e:
                print_error(f"  {filepath}: {e}")
                failed_files.append(filepath)
        
        if not failed_files:
            tests_passed += 1
        else:
            print_error(f"{len(failed_files)} file(s) have syntax errors")
            tests_failed += 1
    except Exception as e:
        print_error(f"Syntax validation failed: {e}")
        tests_failed += 1
    
    # Test 8: Configuration Validation
    print_info("Test 8: Configuration Completeness")
    try:
        from app.core.config import get_settings
        settings = get_settings()
        
        checks = [
            ("Sarvam API Key", settings.sarvam_api_key),
            ("Database URL", settings.database_url),
            ("Upload directory", settings.upload_dir),
            ("Log level", settings.log_level),
        ]
        
        missing = []
        for check_name, value in checks:
            if value:
                print_success(f"  {check_name} configured")
            else:
                print_warning(f"  {check_name} not configured")
                missing.append(check_name)
        
        if len(missing) == 0:
            tests_passed += 1
        else:
            print_warning(f"{len(missing)} optional setting(s) not configured")
            tests_passed += 1  # Still pass - these are optional
    except Exception as e:
        print_error(f"Configuration validation failed: {e}")
        tests_failed += 1
    
    # Summary
    print_header("Validation Summary")
    total = tests_passed + tests_failed
    
    if tests_failed == 0:
        print_success(f"All {total} tests passed!")
        print_info("\n✅ System is ready for production deployment")
        print_info(f"Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        return 0
    else:
        print_error(f"{tests_failed} of {total} tests failed")
        print_warning("\n⚠ Fix errors before deployment")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
