// API Service for Minerva Dashboard
// Connects to Railway backend: minerva-ai-production.up.railway.app

export interface Wallet {
  wallet_address: string;
  name: string;
  telegram: string | null;
  twitter: string | null;
  profit: number;
  wins: number;
  losses: number;
  timeframe: number;
}

export interface Transaction {
  signature: string;
  wallet_address: string;
  wallet_name: string;
  token_address: string;
  action: string;
  amount_sol: number;
  amount_tokens: number;
  platform: string;
  timestamp: string;
}

export interface ApiResponse<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

class MinervaAPI {
  private baseUrl: string;

  constructor(baseUrl: string = 'https://minerva-ai-production.up.railway.app') {
    this.baseUrl = baseUrl;
  }

  setBaseUrl(url: string) {
    this.baseUrl = url;
  }

  async healthCheck(): Promise<{ status: string; service: string; version: string } | null> {
    try {
      const response = await fetch(`${this.baseUrl}/`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Health check failed:', error);
      return null;
    }
  }

  async getWallets(): Promise<Wallet[]> {
    try {
      const response = await fetch(`${this.baseUrl}/api/wallets`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const wallets = await response.json();
      return wallets;
    } catch (error) {
      console.error('Failed to fetch wallets:', error);
      throw error;
    }
  }

  async getTransactions(): Promise<Transaction[]> {
    try {
      const response = await fetch(`${this.baseUrl}/api/transactions`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const transactions = await response.json();
      return transactions;
    } catch (error) {
      console.error('Failed to fetch transactions:', error);
      throw error;
    }
  }
}

// Export singleton instance
export const api = new MinervaAPI();
