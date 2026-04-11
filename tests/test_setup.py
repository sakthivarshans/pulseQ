"""
Initialization Test Module

This exists to ensure that our Pytest pipeline does not fail 
due to "no tests found" when setting up CI.
"""

def test_pytest_setup_functions() -> None:
    """Verifies that the pytest framework is functional."""
    assert True, "Pytest is executing without errors."
