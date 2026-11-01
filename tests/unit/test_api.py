"""
Unit and integration tests for FastAPI REST API endpoints.
Tests system health, auth endpoints, historical queries, backtest runs, and paper trading portfolio.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_system_status_endpoint():
    """Verify system health, execution mode invariant, and zero live trading."""
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["app_name"] == "AlgoTradingResearch"
    assert data["execution_mode"] in ("BACKTEST", "PAPER")
    assert data["live_orders_allowed"] is False


def test_auth_url_endpoint(monkeypatch: pytest.MonkeyPatch):
    """Verify login dialog URL generation when API key is configured."""
    monkeypatch.setattr("app.core.config.settings.UPSTOX_API_KEY", "test_api_key_123")
    response = client.get("/api/v1/auth/url")
    assert response.status_code == 200
    data = response.json()
    assert "authorization_url" in data
    assert "api.upstox.com" in data["authorization_url"]
    assert "client_id=test_api_key_123" in data["authorization_url"]


def test_auth_url_endpoint_missing_credentials(monkeypatch: pytest.MonkeyPatch):
    """Verify informative 400 Bad Request when API key is missing."""
    monkeypatch.setattr("app.core.config.settings.UPSTOX_API_KEY", "")
    monkeypatch.setattr("app.api.routes.auth.auth_manager.api_key", "")
    response = client.get("/api/v1/auth/url")
    assert response.status_code == 400
    assert "UPSTOX_API_KEY is not configured" in response.json()["detail"]


def test_auth_status_endpoint():
    """Verify auth status check response schema."""
    response = client.get("/api/v1/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert "authenticated" in data


def test_backtest_strategies_list():
    """Verify list of available strategies."""
    response = client.get("/api/v1/backtest/strategies")
    assert response.status_code == 200
    strategies = response.json()
    assert "ma_crossover" in strategies
    assert "opening_range_breakout" in strategies


def test_backtest_run_endpoint_on_sample_data():
    """Verify backtest execution over local sample data via REST API."""
    payload = {
        "strategy_name": "ma_crossover",
        "instrument_key": "NSE_FO|NIFTY24O3124500CE",
        "interval": "1minute",
        "initial_capital": 25000.0,
        "slippage_points": 0.5,
        "parameters": {
            "lot_size": 25,
            "stop_loss_points": 10.0,
            "target_points": 25.0,
        },
    }
    response = client.post("/api/v1/backtest/run", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert "backtest_id" in result
    assert "metrics" in result
    assert result["strategy_name"] == "ma_crossover"
    assert result["metrics"]["initial_capital"] == 25000.0


def test_paper_trading_portfolio_endpoint():
    """Verify paper portfolio state endpoint."""
    response = client.get("/api/v1/paper/portfolio")
    assert response.status_code == 200
    data = response.json()
    assert "cash" in data
    assert "equity" in data
    assert "kill_switch_active" in data
    assert "positions" in data


def test_paper_trading_kill_switch_endpoint():
    """Verify paper trading kill switch activation and deactivation."""
    # Activate
    r1 = client.post("/api/v1/paper/kill-switch", json={"active": True, "reason": "Test trigger"})
    assert r1.status_code == 200
    assert r1.json()["kill_switch_active"] is True

    # Deactivate
    r2 = client.post("/api/v1/paper/kill-switch", json={"active": False, "reason": "Reset"})
    assert r2.status_code == 200
    assert r2.json()["kill_switch_active"] is False
