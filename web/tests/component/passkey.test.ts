import { describe, expect, it } from "vitest";

import { MESSAGE_KEYS } from "@/i18n/locale";
import {
  ALGORITHMS, assertionPayload, creationOptions, enrolmentPayload, fromBase64Url,
  hasUsableKey, passkeyState, requestOptions, toBase64Url, usable, type PasskeyFact,
} from "@/lib/passkey";

/**
 * What this app asks a browser for, and what it sends back.
 *
 * **The ceremony itself cannot be tested here** -- `navigator.credentials` does not exist in
 * jsdom and faking it would be asserting a fake. `tests/e2e/passkey.spec.ts` drives a real
 * Chromium virtual authenticator against the real backend, which is the only place a
 * signature is produced and verified. What *is* decided here is everything around it: the
 * options, the encoding and the three fields that cross back to the server action.
 *
 * **The options are where a mistake is silent.** Asking for the wrong thing produces a
 * credential that enrols and can never sign in, and the only evidence is a refusal weeks
 * later -- so each clause the backend depends on is asserted against the reason it exists.
 */

const KEY: PasskeyFact = {
  passkey_id: "p-1",
  label: "Laptop",
  sign_count: 3,
  backed_up: false,
  created_at: "2026-11-01T10:00:00Z",
  last_used_at: "2026-11-20T08:00:00Z",
  revoked_at: null,
};

/** The two shapes a browser hands back, with only the parts this app reads. */
function attestation(options: {
  publicKey?: ArrayBuffer | null;
  authenticatorData?: Uint8Array;
  omitGetPublicKey?: boolean;
} = {}) {
  const response: Record<string, unknown> = {};
  if (!options.omitGetPublicKey) {
    response.getPublicKey = () =>
      options.publicKey === undefined
        ? new Uint8Array([1, 2, 3, 4]).buffer
        : options.publicKey;
  }
  if (options.authenticatorData) {
    const data = options.authenticatorData;
    response.getAuthenticatorData = () => data.buffer.slice(
      data.byteOffset, data.byteOffset + data.byteLength);
  }
  return {
    rawId: new Uint8Array([9, 9, 9, 9]).buffer,
    response,
  } as unknown as PublicKeyCredential;
}

function assertion() {
  return {
    rawId: new Uint8Array([1, 1]).buffer,
    response: {
      clientDataJSON: new Uint8Array([2, 2]).buffer,
      authenticatorData: new Uint8Array([3, 3]).buffer,
      signature: new Uint8Array([4, 4]).buffer,
    },
  } as unknown as PublicKeyCredential;
}

describe("the encoding both halves of the ceremony speak", () => {
  it("is unpadded base64url, which is the only alphabet the backend accepts", () => {
    // **`_b64url` on the server refuses `+`, `/` and padding outright**, because the two
    // alphabets agree on most byte strings and differ on the rest -- so one credential id
    // could decode two ways depending on which decoder saw it, which in a nonce comparison
    // is a replay window. These bytes are chosen to produce `+` and `/` in standard base64.
    const bytes = new Uint8Array([0xfb, 0xff, 0xfe, 0x00, 0x10]);
    const encoded = toBase64Url(bytes);
    expect(encoded).not.toMatch(/[+/=]/);
    expect([...fromBase64Url(encoded)]).toEqual([...bytes]);
  });

  it("round-trips every length, so no input needs padding the server would refuse", () => {
    for (let length = 0; length <= 8; length += 1) {
      const bytes = new Uint8Array(Array.from({ length }, (_, i) => i * 37));
      expect([...fromBase64Url(toBase64Url(bytes))], `length ${length}`).toEqual([...bytes]);
    }
  });

  it("decodes to a buffer WebAuthn will take", () => {
    // **`Uint8Array<ArrayBuffer>`, explicitly.** A plain `new Uint8Array(n)` is typed over
    // `ArrayBufferLike`, which admits a `SharedArrayBuffer` and is therefore not a
    // `BufferSource` -- so a challenge built here would not typecheck where the API wants
    // one. The runtime shape is what this asserts; the type is what the compiler asserts.
    expect(fromBase64Url("AAEC").buffer).toBeInstanceOf(ArrayBuffer);
  });
});

describe("what a credential is created with", () => {
  const options = creationOptions({
    rpName: "Veyro", identityId: "id-1", displayName: "Jane", identifier: "jane@acme.test",
  });

  it("names no relying party, so the browser uses the page's own domain", () => {
    // Sending one would be the client telling the server which relying party to expect, and
    // the backend compares the signed hash against the RP id *it* was configured with -- so
    // a page served from an unexpected domain is refused there rather than trusted here.
    expect(options.rp).toEqual({ name: "Veyro" });
    expect("id" in options.rp).toBe(false);
  });

  it("requires a discoverable credential, because the sign-in sends no credential list", () => {
    // `allowCredentials` would name a person's credential ids to anybody who typed their
    // address, so the ceremony sends none -- which only works if the authenticator can find
    // the credential from the relying party id alone.
    expect(options.authenticatorSelection?.residentKey).toBe("required");
    expect(options.authenticatorSelection?.requireResidentKey).toBe(true);
  });

  it("requires user verification, because the backend refuses an assertion without it", () => {
    // A passkey with no user verification proves possession of a device and says nothing
    // about who holds it, and this build has no factor name for that -- so asking for it
    // later would mean enrolling a credential that can never sign in.
    expect(options.authenticatorSelection?.userVerification).toBe("required");
  });

  it("offers exactly the algorithms the backend will verify", () => {
    // The closed set is what makes `algorithm_for_key` derivable from the stored key: one
    // key type each, so nothing has to be named by the caller. Offering a fourth here would
    // enrol a credential the server refuses at the first assertion.
    expect(options.pubKeyCredParams).toEqual(ALGORITHMS);
    expect(ALGORITHMS.map((one) => one.alg)).toEqual([-7, -8, -257]);
  });

  it("asks for no attestation, because nothing here verifies one", () => {
    expect(options.attestation).toBe("none");
  });

  it("names the account so an authenticator can show which one it is", () => {
    // The browser shows `user.name` when somebody later picks between credentials, which is
    // why `GET /identities/{id}` exists at all: without it the only value available was the
    // identity uuid.
    expect(options.user.name).toBe("jane@acme.test");
    expect(options.user.displayName).toBe("Jane");
    expect(new TextDecoder().decode(options.user.id as Uint8Array)).toBe("id-1");
  });

  it("carries a fresh challenge of its own, which nothing verifies and that is the point", () => {
    // A registration challenge is checked by verifying the *attestation*, which this build
    // deliberately does not do -- so `iam.challenges` has a `passkey_registration` kind that
    // nothing writes. Issuing a server challenge consumed by a path that checks nothing
    // would be a ceremony-shaped control with no control behind it.
    const again = creationOptions({
      rpName: "Veyro", identityId: "id-1", displayName: "Jane", identifier: "jane@acme.test",
    });
    expect((options.challenge as Uint8Array).byteLength).toBe(32);
    expect([...(options.challenge as Uint8Array)])
      .not.toEqual([...(again.challenge as Uint8Array)]);
  });
});

describe("what an assertion is asked for with", () => {
  it("decodes the server's challenge and sends no credential list", () => {
    const challenge = toBase64Url(new Uint8Array([7, 7, 7, 7]));
    const options = requestOptions({ challenge });
    expect([...(options.challenge as Uint8Array)]).toEqual([7, 7, 7, 7]);
    expect(options.allowCredentials).toEqual([]);
    expect(options.userVerification).toBe("required");
    expect("rpId" in options).toBe(false);
  });
});

describe("what crosses back to the server action", () => {
  it("is the credential id, the SPKI key and the backup flag", () => {
    const payload = enrolmentPayload(attestation());
    expect("unsupported" in payload).toBe(false);
    if ("unsupported" in payload) return;
    expect(payload.webauthn_credential_id).toBe(toBase64Url(new Uint8Array([9, 9, 9, 9])));
    expect(payload.public_key).toBe(toBase64Url(new Uint8Array([1, 2, 3, 4])));
  });

  it("says a browser cannot help rather than storing a key the server cannot verify", () => {
    // **`getPublicKey()` is the whole reason no CBOR is parsed anywhere in this build**, so a
    // browser too old to have it cannot enrol a verifiable passkey. Storing the credential
    // anyway would leave somebody with a passkey that fails at every sign-in and no way to
    // tell why.
    expect(enrolmentPayload(attestation({ omitGetPublicKey: true })))
      .toEqual({ unsupported: true });
    expect(enrolmentPayload(attestation({ publicKey: null })))
      .toEqual({ unsupported: true });
  });

  it("reads backup eligibility from bit 0x08, the flag the level is decided by", () => {
    // **BE at 0x08, not BS at 0x10.** The backend's `factor_for` reads eligibility, which is
    // set when the credential is created and never changes; BS says whether it currently *is*
    // backed up and flips the first time a keychain syncs. Nothing updates this column after
    // enrolment, so reading BS listed an eligible-but-unsynced credential -- the ordinary
    // state of a platform passkey for its first few seconds -- as "Stays on this device ·
    // reaches assurance level 3", and the sign-in then gave `passkey_synced` at level 2. The
    // listing's words are about the level, so the flag has to be the one the level follows.
    const flags = (value: number) => {
      const data = new Uint8Array(37);
      data[32] = value;
      return data;
    };
    const eligible = enrolmentPayload(attestation({ authenticatorData: flags(0x08) }));
    const bound = enrolmentPayload(attestation({ authenticatorData: flags(0x04) }));
    // Eligible and not yet synced: BE set, BS clear. This is the case that was wrong.
    const notYetSynced = enrolmentPayload(attestation({ authenticatorData: flags(0x08) }));
    // Synced-state only, which no authenticator should ever send -- BS without BE is
    // forbidden by the specification -- and which must not read as eligible here.
    const bsOnly = enrolmentPayload(attestation({ authenticatorData: flags(0x10) }));
    expect("unsupported" in eligible ? null : eligible.backed_up).toBe(true);
    expect("unsupported" in notYetSynced ? null : notYetSynced.backed_up).toBe(true);
    expect("unsupported" in bound ? null : bound.backed_up).toBe(false);
    expect("unsupported" in bsOnly ? null : bsOnly.backed_up).toBe(false);
  });

  it("reports no backup where the browser cannot say", () => {
    // `getAuthenticatorData` is newer than `getPublicKey`, so the pessimistic answer is the
    // one that under-claims: a credential reported device-bound when nobody knows would tell
    // a member it stays on their phone when it may not.
    const payload = enrolmentPayload(attestation());
    expect("unsupported" in payload ? null : payload.backed_up).toBe(false);
  });

  it("is the four fields of an assertion, each base64url", () => {
    expect(assertionPayload(assertion())).toEqual({
      credential_id: toBase64Url(new Uint8Array([1, 1])),
      client_data_json: toBase64Url(new Uint8Array([2, 2])),
      authenticator_data: toBase64Url(new Uint8Array([3, 3])),
      signature: toBase64Url(new Uint8Array([4, 4])),
    });
  });
});

describe("what the listing says about a passkey", () => {
  it("is in use, unused or withdrawn, and never names a cause it does not have", () => {
    // `iam.passkeys` carries a timestamp and no reason, so a revoked credential is either one
    // the owner withdrew or one the clone check took away and this listing cannot tell them
    // apart. "You withdrew this" about a credential the system revoked after detecting a
    // clone would be the confident wrong answer; the auth log is where a clone shows up.
    expect(passkeyState(KEY)).toBe("in_use");
    expect(passkeyState({ ...KEY, last_used_at: null })).toBe("unused");
    expect(passkeyState({ ...KEY, revoked_at: "2026-11-21T00:00:00Z" })).toBe("withdrawn");
    expect(passkeyState({ ...KEY, last_used_at: null, revoked_at: "2026-11-21T00:00:00Z" }))
      .toBe("withdrawn");
  });

  it("is usable until it is revoked, whatever its counter says", () => {
    expect(usable(KEY)).toBe(true);
    expect(usable({ ...KEY, sign_count: 0, last_used_at: null })).toBe(true);
    expect(usable({ ...KEY, revoked_at: "2026-11-21T00:00:00Z" })).toBe(false);
  });

  it("answers whether this account has a way in that spends nothing", () => {
    // The question the section exists for: a step-up burns a recovery code and there are ten,
    // so a member who spends all of them has no way back from this surface. One usable
    // passkey is a way back that costs nothing.
    expect(hasUsableKey([])).toBe(false);
    expect(hasUsableKey([{ ...KEY, revoked_at: "2026-11-21T00:00:00Z" }])).toBe(false);
    expect(hasUsableKey([{ ...KEY, revoked_at: "2026-11-21T00:00:00Z" }, KEY])).toBe(true);
  });
});

describe("the words this surface renders", () => {
  it("has every one of them in both catalogues", () => {
    // **`MESSAGE_KEYS` compares the two catalogues against each other and is blind to a key
    // no module names**, which is how eight English sentences reached an Arabic page once.
    // So each module asserts its own keys, which is that check run from the side it cannot
    // see.
    const keys = [
      "passkey.heading", "passkey.lead", "passkey.none", "passkey.add", "passkey.adding",
      "passkey.label", "passkey.labelHint", "passkey.added", "passkey.withdraw",
      "passkey.withdrawn", "passkey.ceremonyFailed", "passkey.unsupported",
      "passkey.browserCannot", "passkey.state.unused", "passkey.state.in_use",
      "passkey.state.withdrawn", "passkey.created", "passkey.lastUsed", "passkey.neverUsed",
      "passkey.deviceBound", "passkey.backedUp", "passkey.whyBound", "passkey.signIn",
      "passkey.signingIn", "passkey.needIdentifier", "passkey.signInFailed",
      "passkey.notYetVerified",
    ];
    for (const key of keys) expect(MESSAGE_KEYS, key).toContain(key);
  });

  it("names a state for every value `passkeyState` can return", () => {
    for (const state of ["unused", "in_use", "withdrawn"]) {
      expect(MESSAGE_KEYS, state).toContain(`passkey.state.${state}`);
    }
  });
});
