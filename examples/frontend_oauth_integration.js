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
// Example 2: Create wallet signature (using ethers.js or web3.js)
// ============================================================================

// Using ethers.js v6
async function signMessage(signer, message) {
    const signature = await signer.signMessage(message);
    return signature;
}

// Using wagmi (React hook)
import { useSignMessage } from 'wagmi';

function useOAuthSignature() {
    const { signMessageAsync } = useSignMessage();

    async function createSignature(provider, walletAddress, action = 'Connect') {
        const timestamp = Math.floor(Date.now() / 1000);
        const message = `${action} OAuth provider ${provider} ${action === 'Connect' ? 'to' : 'from'} wallet ${walletAddress.toLowerCase()} at ${timestamp}`;

        const signature = await signMessageAsync({ message });

        return { signature, timestamp };
    }

    return { createSignature };
}

// ============================================================================
// Example 3: Initiate OAuth flow with signature (SECURE VERSION)
// ============================================================================

async function connectGitHub(walletAddress, signer) {
    try {
        // Step 1: Create signature to prove wallet ownership
        const timestamp = Math.floor(Date.now() / 1000);
        const message = `Connect OAuth provider github to wallet ${walletAddress.toLowerCase()} at ${timestamp}`;
        const signature = await signer.signMessage(message);

        // Step 2: Call backend with signature
        const response = await fetch(
            `http://localhost:8000/oauth/connect/github?` +
            `wallet_address=${walletAddress}&` +
            `signature=${signature}&` +
            `timestamp=${timestamp}`
        );
        const data = await response.json();

        // Step 3: Redirect user to GitHub authorization page
        window.location.href = data.auth_url;

        // User will be redirected back to: 
        // http://localhost:3000/oauth/result?success=true&provider=github
        // (or with success=false and an error parameter)

    } catch (error) {
        console.error("Error initiating OAuth:", error);
    }
}

// ============================================================================
// Example 4: Handle OAuth callback in your frontend
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
// Example 5: Disconnect GitHub with signature (SECURE VERSION)
// ============================================================================

async function disconnectGitHub(walletAddress, signer) {
    try {
        // Step 1: Create signature to prove wallet ownership
        const timestamp = Math.floor(Date.now() / 1000);
        const message = `Disconnect OAuth provider github from wallet ${walletAddress.toLowerCase()} at ${timestamp}`;
        const signature = await signer.signMessage(message);

        // Step 2: Call backend with signature
        const response = await fetch(
            `http://localhost:8000/oauth/disconnect/github/${walletAddress}?` +
            `signature=${signature}&` +
            `timestamp=${timestamp}`,
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
// Example 6: Complete React component with wagmi hooks (SECURE VERSION)
// ============================================================================

import React, { useState, useEffect } from 'react';
import { useAccount, useSignMessage } from 'wagmi';

function GitHubConnectionButton() {
    const { address } = useAccount();
    const { signMessageAsync } = useSignMessage();
    const [isConnected, setIsConnected] = useState(false);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (address) {
            checkConnection();
        }
    }, [address]);

    async function checkConnection() {
        setLoading(true);
        try {
            const response = await fetch(
                `http://localhost:8000/oauth/status/github/${address}`
            );
            const data = await response.json();
            setIsConnected(data.has_credentials);
        } catch (error) {
            console.error("Error:", error);
        }
        setLoading(false);
    }

    async function handleConnect() {
        try {
            // Create signature
            const timestamp = Math.floor(Date.now() / 1000);
            const message = `Connect OAuth provider github to wallet ${address.toLowerCase()} at ${timestamp}`;
            const signature = await signMessageAsync({ message });

            // Get auth URL
            const response = await fetch(
                `http://localhost:8000/oauth/connect/github?` +
                `wallet_address=${address}&` +
                `signature=${signature}&` +
                `timestamp=${timestamp}`
            );
            const data = await response.json();

            // Redirect to GitHub
            window.location.href = data.auth_url;
        } catch (error) {
            console.error("Error connecting:", error);
            alert("Failed to connect. Please try again.");
        }
    }

    async function handleDisconnect() {
        if (!confirm("Are you sure you want to disconnect GitHub?")) return;

        try {
            // Create signature
            const timestamp = Math.floor(Date.now() / 1000);
            const message = `Disconnect OAuth provider github from wallet ${address.toLowerCase()} at ${timestamp}`;
            const signature = await signMessageAsync({ message });

            // Call disconnect endpoint
            await fetch(
                `http://localhost:8000/oauth/disconnect/github/${address}?` +
                `signature=${signature}&` +
                `timestamp=${timestamp}`,
                { method: 'DELETE' }
            );

            setIsConnected(false);
        } catch (error) {
            console.error("Error disconnecting:", error);
            alert("Failed to disconnect. Please try again.");
        }
    }

    if (!address) return <div>Please connect your wallet</div>;
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
