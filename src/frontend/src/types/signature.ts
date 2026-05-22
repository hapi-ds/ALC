/**
 * TypeScript types for the Electronic Signatures feature.
 *
 * These types mirror the backend Pydantic schemas defined in
 * src/backend/src/alcoabase/schemas/signature.py and are used by
 * the signatureStore and signature UI components.
 *
 * References:
 *   - Design doc: Data Models section
 *   - 21 CFR Part 11: Electronic records and signatures
 */

/** Reason categories compliant with 21 CFR Part 11 */
export type SignatureReasonCategory = "Author" | "Review" | "Approval";

/** Visual stamp data embedded in the signed PDF */
export interface SignatureStamp {
  signer_name: string;
  signed_at: string; // ISO 8601
  reason: string;
  transition: string;
}

/** Response from POST /api/signatures/sign */
export interface SignResponse {
  success: boolean;
  signature_hash: string;
  signature_record_id: number | null;
  stamp: SignatureStamp;
  certificate_subject?: string | null;
  certificate_issuer?: string | null;
  certificate_serial?: string | null;
}

/** Response from GET /api/signatures/records/{document_uuid} */
export interface SignatureRecordResponse {
  id: number;
  document_uuid: string;
  signer_user_id: number;
  transition: string;
  reason: string | null;
  signed_at: string; // ISO 8601
  signature_hash: string;
  certificate_subject?: string | null;
  certificate_issuer?: string | null;
  certificate_serial?: string | null;
  signature_mode?: "pades" | "hash";
}

/** Context passed when opening the signature dialog */
export interface SignatureDialogContext {
  document_uuid: string;
  document_version_id: number;
  transition: string;
  documentTitle: string;
}

/** Response from POST /api/v1/auth/re-authenticate */
export interface ReAuthResponse {
  verified: boolean;
  signature_token: string;
  expires_in: number;
}

/** Response from GET /api/signatures/verify/{document_uuid} */
export interface VerifyResponse {
  is_valid: boolean;
  signature_count: number;
  signatures: VerifySignatureEntry[];
  tampered_from_index: number;
}

/** Individual signature entry in the verify response */
export interface VerifySignatureEntry {
  signer_name: string;
  signed_at: string;
  reason: string;
  is_valid: boolean;
  certificate_subject?: string | null;
  certificate_issuer?: string | null;
}
