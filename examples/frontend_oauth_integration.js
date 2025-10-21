/*
Frontend Integration Example for OAuth Flow

This file demonstrates how to integrate the OAuth flow in your frontend.
Not meant to be run, just for reference.
*/

// ============================================================================
// Example 1: Check if user has GitHub credentials
// ============================================================================

async function checkGitHubCredentials(walletAddress) {
    try {
        const response = await fetch(
            `http://localhost:8000/oauth/status/github/${walletAddress}`
        );
        const data = await response.json();

        if (data.has_credentials) {
            console.log("User has valid GitHub credentials!");
            return true;
        } else {
            console.log("User needs to connect GitHub");
            return false;
        }
    } catch (error) {
        console.error("Error checking credentials:", error);
        return false;
    }
}

// ============================================================================
// Example 2: Initiate OAuth flow (link GitHub account)
// ============================================================================

async function connectGitHub(walletAddress) {
    try {
        const response = await fetch(
            `http://localhost:8000/oauth/connect/github?wallet_address=${walletAddress}`
        );
        const data = await response.json();

        // Redirect user to GitHub authorization page
        window.location.href = data.auth_url;

        // User will be redirected back to: 
        // http://localhost:3000/oauth/result?success=true&provider=github
        // (or with success=false and an error parameter)

    } catch (error) {
        console.error("Error initiating OAuth:", error);
    }
}

// ============================================================================
// Example 3: Handle OAuth callback in your frontend
// ============================================================================

// Create a route in your frontend: /oauth/result
// This is where users land after authorizing on GitHub

function OAuthResultPage() {
    const searchParams = new URLSearchParams(window.location.search);
    const success = searchParams.get('success') === 'true';
    const provider = searchParams.get('provider');
    const error = searchParams.get('error');

    if (success) {
        return (
            <div>
                <h1>Success!</h1>
                <p>Your {provider} account has been linked.</p>
                <button onClick={() => window.location.href = '/dashboard'}>
                    Go to Dashboard
                </button>
            </div>
        );
    } else {
        return (
            <div>
                <h1>Authentication Failed</h1>
                <p>Error: {error}</p>
                <button onClick={() => window.location.href = '/settings'}>
                    Try Again
                </button>
            </div>
        );
    }
}

// ============================================================================
// Example 4: Disconnect GitHub (remove credentials)
// ============================================================================

async function disconnectGitHub(walletAddress) {
    try {
        const response = await fetch(
            `http://localhost:8000/oauth/disconnect/github/${walletAddress}`,
            { method: 'DELETE' }
        );
        const data = await response.json();

        if (data.success) {
            console.log("GitHub account disconnected");
            return true;
        }
    } catch (error) {
        console.error("Error disconnecting:", error);
        return false;
    }
}

// ============================================================================
// Example 5: Complete React component example
// ============================================================================

import React, { useState, useEffect } from 'react';

function GitHubConnectionButton({ walletAddress }) {
    const [isConnected, setIsConnected] = useState(false);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        checkConnection();
    }, [walletAddress]);

    async function checkConnection() {
        setLoading(true);
        try {
            const response = await fetch(
                `http://localhost:8000/oauth/status/github/${walletAddress}`
            );
            const data = await response.json();
            setIsConnected(data.has_credentials);
        } catch (error) {
            console.error("Error:", error);
        }
        setLoading(false);
    }

    async function handleConnect() {
        const response = await fetch(
            `http://localhost:8000/oauth/connect/github?wallet_address=${walletAddress}`
        );
        const data = await response.json();
        window.location.href = data.auth_url;
    }

    async function handleDisconnect() {
        if (!confirm("Are you sure you want to disconnect GitHub?")) return;

        await fetch(
            `http://localhost:8000/oauth/disconnect/github/${walletAddress}`,
            { method: 'DELETE' }
        );
        setIsConnected(false);
    }

    if (loading) return <div>Loading...</div>;

    return (
        <div>
            {isConnected ? (
                <div>
                    <span>✓ GitHub Connected</span>
                    <button onClick={handleDisconnect}>Disconnect</button>
                </div>
            ) : (
                <button onClick={handleConnect}>Connect GitHub</button>
            )}
        </div>
    );
}

export default GitHubConnectionButton;
