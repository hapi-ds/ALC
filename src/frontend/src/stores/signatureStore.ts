/**
 * Electronic Signatures Store (Zustand)
 *
 * Centralized state management for electronic signature operations:
 * re-authentication, signing, token lifecycle, signature records,
 * verification, and dialog state.
 *
 * Requirements: 9.1–9.11, 12.2, 12.5, 12.6
 */

import { create } from "zustand";
import { apiClient } from "../lib/apiClient";
import { extractErrorMessage } from "../lib/signatureUtils";
import type {
  SignResponse,
  SignatureRecordResponse,
  SignatureDialogContext,
  ReAuthResponse,
  VerifyResponse,
} from "../types/signature";

// ---------------------------------------------------------------------------
// State Interface
// ---------------------------------------------------------------------------

export interface SignatureStoreState {
  // Re-authentication
  isReAuthenticating: boolean;
  reAuthError: string | null;
  signatureToken: string | null;
  tokenExpiresAt: number | null; // Unix timestamp ms

  // Signing
  isSigning: boolean;
  signError: string | null;
  lastSignResult: SignResponse | null;

  // Signature records (keyed by document_uuid)
  records: Record<string, SignatureRecordResponse[]>;
  isLoadingRecords: boolean;
  recordsError: string | null;

  // Token countdown
  remainingSeconds: number;

  // Dialog state
  isDialogOpen: boolean;
  dialogContext: SignatureDialogContext | null;

  // Password retained for signing step
  _password: string | null;

  // Verification
  isVerifying: boolean;
  verifyError: string | null;
  verifyResult: VerifyResponse | null;

  // Actions
  openSignatureDialog: (context: SignatureDialogContext) => void;
  closeSignatureDialog: () => void;
  reAuthenticate: (password: string) => Promise<void>;
  signDocument: (
    document_uuid: string,
    document_version_id: number,
    transition: string,
    reason: string,
    password: string
  ) => Promise<void>;
  fetchSignatureRecords: (document_uuid: string) => Promise<void>;
  verifySignatures: (document_uuid: string) => Promise<void>;
  startTokenCountdown: () => void;
  clearToken: () => void;
  reset: () => void;
}

// ---------------------------------------------------------------------------
// Module-level interval ID for countdown (not stored in state)
// ---------------------------------------------------------------------------

let countdownIntervalId: ReturnType<typeof setInterval> | null = null;

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useSignatureStore = create<SignatureStoreState>((set, get) => ({
  // Re-authentication
  isReAuthenticating: false,
  reAuthError: null,
  signatureToken: null,
  tokenExpiresAt: null,

  // Signing
  isSigning: false,
  signError: null,
  lastSignResult: null,

  // Signature records
  records: {},
  isLoadingRecords: false,
  recordsError: null,

  // Token countdown
  remainingSeconds: 0,

  // Dialog state
  isDialogOpen: false,
  dialogContext: null,

  // Password
  _password: null,

  // Verification
  isVerifying: false,
  verifyError: null,
  verifyResult: null,

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  openSignatureDialog: (context: SignatureDialogContext) => {
    const { isDialogOpen, closeSignatureDialog } = get();

    // If already open, close first to reset prior state
    if (isDialogOpen) {
      closeSignatureDialog();
    }

    set({ isDialogOpen: true, dialogContext: context });
  },

  closeSignatureDialog: () => {
    const { clearToken } = get();
    clearToken();
    set({
      isDialogOpen: false,
      dialogContext: null,
      signError: null,
      lastSignResult: null,
    });
  },

  reAuthenticate: async (password: string) => {
    set({ isReAuthenticating: true, reAuthError: null });

    try {
      const response = await apiClient.post<ReAuthResponse>(
        "/api/v1/auth/re-authenticate",
        { password },
        { changeReason: "Re-authentication for electronic signature" }
      );

      const tokenExpiresAt = Date.now() + response.expires_in * 1000;

      set({
        signatureToken: response.signature_token,
        tokenExpiresAt,
        _password: password,
        isReAuthenticating: false,
      });

      // Start the countdown after storing state
      get().startTokenCountdown();
    } catch (error) {
      set({
        reAuthError: extractErrorMessage(error),
        isReAuthenticating: false,
      });
    }
  },

  signDocument: async (
    document_uuid: string,
    document_version_id: number,
    transition: string,
    reason: string,
    password: string
  ) => {
    set({ isSigning: true, signError: null });

    try {
      const response = await apiClient.post<SignResponse>(
        "/api/signatures/sign",
        {
          document_uuid,
          document_version_id,
          transition,
          reason,
          password,
        },
        { changeReason: `Electronic signature: ${transition}` }
      );

      set({
        lastSignResult: response,
        isSigning: false,
      });
    } catch (error) {
      set({
        signError: extractErrorMessage(error),
        isSigning: false,
      });
    }
  },

  fetchSignatureRecords: async (document_uuid: string) => {
    set({ isLoadingRecords: true, recordsError: null });

    try {
      const response = await apiClient.get<SignatureRecordResponse[]>(
        `/api/signatures/records/${document_uuid}`
      );

      set((state) => ({
        records: { ...state.records, [document_uuid]: response },
        isLoadingRecords: false,
      }));
    } catch (error) {
      set({
        recordsError: extractErrorMessage(error),
        isLoadingRecords: false,
      });
    }
  },

  verifySignatures: async (document_uuid: string) => {
    set({ isVerifying: true, verifyError: null });

    try {
      const response = await apiClient.get<VerifyResponse>(
        `/api/signatures/verify/${document_uuid}`
      );

      set({
        verifyResult: response,
        isVerifying: false,
      });
    } catch (error) {
      set({
        verifyError: extractErrorMessage(error),
        isVerifying: false,
      });
    }
  },

  startTokenCountdown: () => {
    // Clear any existing interval
    if (countdownIntervalId !== null) {
      clearInterval(countdownIntervalId);
      countdownIntervalId = null;
    }

    const { tokenExpiresAt } = get();
    if (tokenExpiresAt === null) return;

    // Compute initial remaining seconds
    const remaining = Math.floor((tokenExpiresAt - Date.now()) / 1000);
    set({ remainingSeconds: Math.max(remaining, 0) });

    if (remaining <= 0) {
      set({ signatureToken: null, tokenExpiresAt: null });
      return;
    }

    countdownIntervalId = setInterval(() => {
      const { tokenExpiresAt: expiresAt } = get();
      if (expiresAt === null) {
        if (countdownIntervalId !== null) {
          clearInterval(countdownIntervalId);
          countdownIntervalId = null;
        }
        return;
      }

      const secs = Math.floor((expiresAt - Date.now()) / 1000);

      if (secs <= 0) {
        if (countdownIntervalId !== null) {
          clearInterval(countdownIntervalId);
          countdownIntervalId = null;
        }
        set({
          remainingSeconds: 0,
          signatureToken: null,
          tokenExpiresAt: null,
        });
      } else {
        set({ remainingSeconds: secs });
      }
    }, 1000);
  },

  clearToken: () => {
    if (countdownIntervalId !== null) {
      clearInterval(countdownIntervalId);
      countdownIntervalId = null;
    }
    set({
      signatureToken: null,
      tokenExpiresAt: null,
      remainingSeconds: 0,
    });
  },

  reset: () => {
    if (countdownIntervalId !== null) {
      clearInterval(countdownIntervalId);
      countdownIntervalId = null;
    }
    set({
      isReAuthenticating: false,
      reAuthError: null,
      signatureToken: null,
      tokenExpiresAt: null,
      isSigning: false,
      signError: null,
      lastSignResult: null,
      records: {},
      isLoadingRecords: false,
      recordsError: null,
      remainingSeconds: 0,
      isDialogOpen: false,
      dialogContext: null,
      _password: null,
      isVerifying: false,
      verifyError: null,
      verifyResult: null,
    });
  },
}));
