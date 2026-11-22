/**
 * The WebAuthn ceremony's client half: what to ask the browser for, and what to send back.
 *
 * **Decisions only, and no imports that reach `next/headers`.** A client component cannot
 * import a module that touches the request, and this repository has paid for that twice: the
 * account page's first version put its decisions beside its fetchers and the *login* page
 * started answering 500. `passkey-reads.ts` holds the I/O.
 *
 * **Every binary value crossing the wire is unpadded base64url**, which is what the backend's
 * `_b64url` accepts and nothing else: the standard alphabet's `+` and `/` are refused outright,
 * because the two alphabets agree on most byte strings and differ on the rest, so accepting
 * either would mean one credential decoding two ways.
 *
 * **The enrolment ceremony's challenge is generated here and is not verified anywhere**, and
 * that is a statement rather than an oversight. A registration challenge is checked by
 * verifying the *attestation*, which this build deliberately does not do -- it has no AAGUID
 * metadata service and no policy about which authenticators a tenant accepts. `iam.challenges`
 * admits a `passkey_registration` kind and nothing writes one, for exactly that reason: a
 * server challenge consumed by a path that checks nothing would be a control-shaped column
 * with no control behind it, which is the shape this build refuses elsewhere. What makes an
 * enrolment safe is that it happens inside an authenticated, self-scoped session, and what
 * makes the credential trustworthy afterwards is that every *assertion* is verified.
 */

/** The COSE algorithms the backend will verify, in the order a browser should prefer them. */
export const ALGORITHMS = [
  { type: "public-key" as const, alg: -7 },    // ES256, every platform authenticator
  { type: "public-key" as const, alg: -8 },    // Ed25519, several security keys
  { type: "public-key" as const, alg: -257 },  // RS256, older Windows Hello
];

export function toBase64Url(raw: ArrayBuffer | Uint8Array): string {
  const bytes = raw instanceof Uint8Array ? raw : new Uint8Array(raw);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function fromBase64Url(value: string): Uint8Array<ArrayBuffer> {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/")
    + "=".repeat((4 - (value.length % 4)) % 4);
  const binary = atob(padded);
  // **`Uint8Array<ArrayBuffer>`, explicitly.** A plain `new Uint8Array(n)` is typed over
  // `ArrayBufferLike`, which admits a `SharedArrayBuffer` and is therefore not a `BufferSource`
  // -- so a challenge built here would not typecheck where WebAuthn wants one. The buffer is
  // constructed first so its type is the narrow one.
  const bytes = new Uint8Array(new ArrayBuffer(binary.length));
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/**
 * Whether this browser can do a ceremony at all.
 *
 * **`PublicKeyCredential` as well as `credentials`**, because the second exists in browsers
 * that have no WebAuthn at all -- `navigator.credentials` carries the password manager API too,
 * so checking only that reports a browser as capable and then throws at the ceremony.
 */
export function available(): boolean {
  return typeof window !== "undefined"
    && typeof window.PublicKeyCredential === "function"
    && typeof navigator !== "undefined"
    && typeof navigator.credentials?.create === "function";
}

/**
 * Options for creating a credential, which the browser hands to the authenticator.
 *
 * **No `rp.id`, deliberately.** Omitting it makes the browser use the page's own effective
 * domain, which is the right answer and means this client needs no configuration at all: the
 * backend compares the signed `rpIdHash` against the RP id *it* was configured with, so a page
 * served from a domain the backend does not expect is refused there. Sending an id from here
 * would be the client telling the server which relying party to expect, which is the shape
 * every other control in this build refuses.
 */
export function creationOptions(args: {
  rpName: string;
  identityId: string;
  displayName: string;
  identifier: string;
}): PublicKeyCredentialCreationOptions {
  return {
    // Not verified anywhere -- see this module's own header for why that is a statement.
    challenge: crypto.getRandomValues(new Uint8Array(32)),
    rp: { name: args.rpName },
    user: {
      // The identity id, so an authenticator that already holds a credential for this account
      // replaces it rather than adding a second one nobody asked for.
      id: new TextEncoder().encode(args.identityId),
      name: args.identifier,
      displayName: args.displayName,
    },
    pubKeyCredParams: ALGORITHMS,
    authenticatorSelection: {
      // **Discoverable, because the server deliberately returns no credential list.**
      // `allowCredentials` would name a person's credential ids to anybody who typed their
      // address, so the sign-in ceremony sends none -- which only works if the authenticator
      // can find the credential from the relying party id alone.
      residentKey: "required",
      requireResidentKey: true,
      // **Required, because the backend refuses an assertion without it.** A passkey with no
      // user verification proves possession of a device and says nothing about who holds it,
      // and there is no factor name for that -- so asking for it later would mean enrolling a
      // credential that can never sign in.
      userVerification: "required",
    },
    // No attestation is verified, so asking for one would collect a statement nobody reads.
    attestation: "none",
    timeout: 120_000,
  };
}

/** Options for signing in, with the challenge the server issued and no relying party id. */
export function requestOptions(args: { challenge: string }): PublicKeyCredentialRequestOptions {
  return {
    challenge: fromBase64Url(args.challenge),
    // Empty, deliberately: see `creationOptions`.
    allowCredentials: [],
    userVerification: "required",
    timeout: 120_000,
  };
}

export type EnrolmentPayload = {
  webauthn_credential_id: string;
  public_key: string;
  backed_up: boolean;
};

/**
 * What to POST after a creation ceremony, or `null` with a reason this browser cannot.
 *
 * **`getPublicKey()` is the whole reason no CBOR is parsed anywhere in this build.** It returns
 * SPKI DER, which the backend loads directly; the alternative is decoding the attestation
 * object's COSE key, and a CBOR decoder in the authentication path is a larger attack surface
 * than the key it decodes. A browser too old to have it cannot enrol a verifiable passkey, and
 * saying so is better than storing a credential that can never sign in.
 */
export function enrolmentPayload(
  credential: PublicKeyCredential,
): EnrolmentPayload | { unsupported: true } {
  const response = credential.response as AuthenticatorAttestationResponse;
  if (typeof response.getPublicKey !== "function") return { unsupported: true };
  const key = response.getPublicKey();
  if (key === null) return { unsupported: true };
  return {
    webauthn_credential_id: toBase64Url(credential.rawId),
    public_key: toBase64Url(key),
    // **The same flag the factor is decided by**, so the listing cannot promise a level the
    // next sign-in will not give. Which factor an assertion presents is still decided per
    // assertion from the signed flags; this is the enrolment-time copy the listing reads.
    backed_up: backupEligible(credential),
  };
}

/**
 * Backup **eligibility**, which is the flag that decides the level.
 *
 * **`BE` at 0x08, not `BS` at 0x10, and the two differ in a way the listing would lie about.**
 * The backend's `factor_for` reads `BE`: eligibility is set when the credential is created and
 * never changes, while `BS` says whether it currently *is* backed up and flips the first time
 * somebody turns a keychain on. This value is written once at enrolment and nothing updates it
 * afterwards, so a credential that is eligible but not yet synced -- the ordinary state of a
 * platform passkey before the keychain finishes -- read `BS` as false, was listed as "Stays on
 * this device · reaches assurance level 3", and then signed in as `passkey_synced` at level 2.
 * The listing's own words are about the level, so the flag behind them has to be the one the
 * level is decided by. Found by reading the two together.
 */
function backupEligible(credential: PublicKeyCredential): boolean {
  const response = credential.response as AuthenticatorAttestationResponse;
  if (typeof response.getAuthenticatorData !== "function") return false;
  const data = new Uint8Array(response.getAuthenticatorData());
  // Byte 32 is the flags byte; 0x08 is BE, "eligible for backup".
  return data.length > 32 && (data[32]! & 0x08) !== 0;
}

export type AssertionPayload = {
  credential_id: string;
  client_data_json: string;
  authenticator_data: string;
  signature: string;
};

/** What to POST after a sign-in ceremony. */
export function assertionPayload(credential: PublicKeyCredential): AssertionPayload {
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    credential_id: toBase64Url(credential.rawId),
    client_data_json: toBase64Url(response.clientDataJSON),
    authenticator_data: toBase64Url(response.authenticatorData),
    signature: toBase64Url(response.signature),
  };
}

export type PasskeyFact = {
  passkey_id: string;
  label: string | null;
  sign_count: number;
  backed_up: boolean;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
};

/** Whether this credential can still open a session. */
export function usable(passkey: PasskeyFact): boolean {
  return passkey.revoked_at === null;
}

/**
 * What a reader is told about a passkey, beyond its label.
 *
 * **Three states, and the third is the one worth separating.** A revoked credential is either
 * one the owner withdrew or one the clone check took away, and this listing cannot tell them
 * apart -- `iam.passkeys` carries a timestamp and no reason, and the reason is on the auth log
 * instead. So the marker says "withdrawn" rather than naming a cause it does not have, and the
 * log below it is where a clone shows up. Saying "you withdrew this" about a credential the
 * system revoked after detecting a clone would be the confident wrong answer.
 */
export function passkeyState(passkey: PasskeyFact): "unused" | "in_use" | "withdrawn" {
  if (passkey.revoked_at !== null) return "withdrawn";
  return passkey.last_used_at === null ? "unused" : "in_use";
}

/**
 * Whether this account still has a way in that is not a recovery code.
 *
 * The question the account page exists to answer after MOD-007's recorded dead end: a step-up
 * spends a recovery code, reissuing needs a stepped-up session, so a member who spends all ten
 * has no way back. One usable passkey is a way back that spends nothing.
 */
export function hasUsableKey(passkeys: PasskeyFact[]): boolean {
  return passkeys.some(usable);
}
