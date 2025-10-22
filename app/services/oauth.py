"""
Modular OAuth service for handling different providers.
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import requests
from urllib.parse import urlencode
from app.core.config import settings


class OAuthProvider(ABC):
    """Base class for OAuth providers."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the provider name (e.g., 'github')."""
        pass

    @abstractmethod
    def get_authorization_url(self, state: str) -> str:
        """Generate the OAuth authorization URL."""
        pass

    @abstractmethod
    def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.
        Returns dict with: access_token, refresh_token (optional), expires_in (optional), scopes (optional)
        """
        pass

    @abstractmethod
    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Fetch user info using the access token.
        Returns dict with provider-specific user data.
        """
        pass


class GitHubOAuthProvider(OAuthProvider):
    """GitHub OAuth implementation."""

    def __init__(self):
        self.client_id = settings.GITHUB_CLIENT_ID
        self.client_secret = settings.GITHUB_CLIENT_SECRET
        # OAuth callback must go to backend first, then backend redirects to frontend
        base = settings.BACKEND_URL or "http://localhost:8000"
        self.redirect_uri = f"{base.rstrip('/')}/oauth/callback/github"
        self.scope = "user:email"

    def get_provider_name(self) -> str:
        return "github"

    def get_authorization_url(self, state: str) -> str:
        """Generate GitHub OAuth authorization URL."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
            "state": state,
        }
        return f"https://github.com/login/oauth/authorize?{urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for GitHub access token."""
        response = requests.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": self.redirect_uri,
            },
        )
        response.raise_for_status()
        data = response.json()

        # GitHub returns: access_token, token_type, scope
        return {
            "access_token": data.get("access_token"),
            "refresh_token": None,  # GitHub doesn't provide refresh tokens by default
            "expires_in": None,  # GitHub tokens don't expire
            "scopes": data.get("scope", "").split(",") if data.get("scope") else [],
        }

    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Fetch GitHub user information."""
        response = requests.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        response.raise_for_status()
        return response.json()


class OAuthService:
    """Service to manage OAuth flows for different providers."""

    def __init__(self):
        self._providers: Dict[str, OAuthProvider] = {}
        self._register_providers()

    def _register_providers(self):
        """Register all available OAuth providers."""
        if settings.GITHUB_CLIENT_ID and settings.GITHUB_CLIENT_SECRET:
            self._providers["github"] = GitHubOAuthProvider()

    def get_provider(self, provider_name: str) -> Optional[OAuthProvider]:
        """Get OAuth provider by name."""
        return self._providers.get(provider_name.lower())

    def list_providers(self) -> list[str]:
        """List all registered providers."""
        return list(self._providers.keys())


# Global instance
oauth_service = OAuthService()
