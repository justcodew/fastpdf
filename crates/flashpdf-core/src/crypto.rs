//! PDF encryption / decryption (PDF spec §7.6).
//!
//! Supports the two common variants — RC4 (V1/V2, R=2/3) and AES-128 (V4, R=4)
//! — using the standard empty-user-password fast path that covers the vast
//! majority of "encrypted but readable" PDFs (browser exports, scanned PDFs
//! with permission locks, etc.). AES-256 (V5/R6) is detected but reported as
//! unsupported; users get a clear error rather than a silent fatal.
//!
//! The transform is per-object: each String / HexString / Stream body is
//! decrypted with an object key derived from (file_key, obj_num, obj_gen).
//! Strings inside the `/Encrypt` dict itself, xref-stream contents, and
//! ObjStm index bytes are exempt.
//!
//! Implementations follow PDF spec §7.6.3.3 (algorithm 2), §7.6.3.4
//! (algorithms 3/4/5), §7.6.2 (RC4), §7.6.3.2 (AES object key).

use crate::parser::ParseError;
use crate::types::PdfObject;
use md5::{Digest, Md5};

/// The 32-byte padding string defined in PDF spec §7.6.3.3.
const PAD: [u8; 32] = [
    0x28, 0xBF, 0x4E, 0x5E, 0x4E, 0x75, 0x8A, 0x41, 0x64, 0x00, 0x4E, 0x56, 0xFF, 0xFA, 0x01, 0x08,
    0x2E, 0x2E, 0x00, 0xB6, 0xD0, 0x68, 0x3E, 0x80, 0x2F, 0x0C, 0xA9, 0xFE, 0x64, 0x53, 0x69, 0x7A,
];

/// Decryption algorithm in use.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Algorithm {
    /// RC4 stream cipher (V1/V2, R=2 or R=3).
    RC4,
    /// AES-128 in CBC mode with PKCS#7 padding (V4, R=4).
    Aes128,
}

/// Compiled decryption state. Constructed once from `/Encrypt` + document ID
/// and reused for every object lookup.
#[derive(Debug, Clone)]
pub struct Decryptor {
    pub algorithm: Algorithm,
    /// File-level key (16 bytes typical; depends on /Length).
    file_key: Vec<u8>,
    pub revision: i64,
}

impl Decryptor {
    /// Build from the `/Encrypt` dictionary.
    ///
    /// `doc_id_first` is the first element of the trailer `/ID` array — used
    /// as a salt during key derivation. Tries the empty user password; if that
    /// fails to validate against `/U`, returns an error so callers can surface
    /// "password required" rather than silently producing garbage.
    pub fn from_encrypt_dict(
        encrypt: &PdfObject<'_>,
        doc_id_first: &[u8],
    ) -> Result<Self, ParseError> {
        // Only the standard security handler is supported.
        let filter = encrypt
            .get(b"Filter")
            .and_then(|v| v.as_name())
            .unwrap_or(b"");
        if filter != b"Standard" {
            return Err(ParseError::Message(format!(
                "unsupported /Filter {:?} (only /Standard is implemented)",
                std::str::from_utf8(filter).unwrap_or("<utf8>")
            )));
        }

        let v = encrypt.get(b"V").and_then(|v| v.as_i64()).unwrap_or(0);
        let r = encrypt.get(b"R").and_then(|v| v.as_i64()).unwrap_or(0);
        let algorithm = match (v, r) {
            (1, 2) | (2, 3) => Algorithm::RC4,
            (4, 4) => Algorithm::Aes128,
            (5, 6) => {
                return Err(ParseError::Message(
                    "AES-256 encryption (V5/R6) is not yet supported".into(),
                ));
            }
            _ => {
                return Err(ParseError::Message(format!(
                    "unsupported encryption V={v} R={r}"
                )));
            }
        };

        // /Length is in bits; default 40 for V1/V2.
        let length_bits = encrypt
            .get(b"Length")
            .and_then(|v| v.as_i64())
            .unwrap_or(40);
        let length_bytes = (length_bits.max(40).min(128) / 8) as usize;

        let o = get_padded_bytes(encrypt.get(b"O"), 32);
        let u = get_padded_bytes(encrypt.get(b"U"), 32);
        let p = encrypt.get(b"P").and_then(|v| v.as_i64()).unwrap_or(0) as u32;

        let encrypt_metadata = encrypt
            .get(b"EncryptMetadata")
            .and_then(|v| v.as_bool())
            .unwrap_or(true);

        // Algorithm 2: derive file key from empty user password.
        let file_key = derive_file_key(b"", &o, p, doc_id_first, r, length_bytes, encrypt_metadata);

        let dec = Decryptor {
            algorithm,
            file_key,
            revision: r,
        };

        // Validate against /U (Algorithm 4 for R=2, Algorithm 5 for R>=3).
        if !validate_user_password(&dec, &u, doc_id_first) {
            return Err(ParseError::Message(
                "PDF requires a non-empty user password (not supported)".into(),
            ));
        }

        Ok(dec)
    }

    /// Decrypt the bytes of a single object (string or stream body).
    pub fn decrypt_object(&self, obj_num: u32, obj_gen: u16, data: &[u8]) -> Vec<u8> {
        let obj_key = derive_object_key(&self.file_key, obj_num, obj_gen, self.algorithm);
        match self.algorithm {
            Algorithm::RC4 => rc4(&obj_key, data),
            Algorithm::Aes128 => {
                // AES object key has 9 salt bytes appended; the first 16 bytes
                // of ciphertext are the IV (PDF spec §7.6.2, figure 2).
                aes_128_cbc_decrypt(&obj_key, data)
            }
        }
    }
}

fn get_padded_bytes(obj: Option<&PdfObject<'_>>, len: usize) -> Vec<u8> {
    match obj {
        Some(PdfObject::String(s)) => {
            // Literal `(…)` strings may contain octal/escape sequences; the
            // parser stores them raw, so unescape before crypto use.
            let mut v = crate::document::unescape_literal_string(s);
            if v.len() < len {
                v.resize(len, 0);
            }
            v
        }
        Some(PdfObject::HexString(s)) => {
            // HexString is stored as raw ASCII hex text by the parser; decode
            // to binary. /O and /U are 32-byte values usually emitted as hex
            // because they contain arbitrary bytes.
            let mut v = crate::document::hex_decode(s).unwrap_or_else(|| s.to_vec());
            if v.len() < len {
                v.resize(len, 0);
            }
            v
        }
        _ => vec![0u8; len],
    }
}

/// PDF spec Algorithm 2: compute the file encryption key from the user
/// password, /O, /P, /ID[0], and (R>=4 only) EncryptMetadata flag.
fn derive_file_key(
    password: &[u8],
    o: &[u8],
    p: u32,
    id0: &[u8],
    revision: i64,
    length_bytes: usize,
    encrypt_metadata: bool,
) -> Vec<u8> {
    // Step 1: pad/truncate password to 32 bytes.
    let mut padded = [0u8; 32];
    let pw_len = password.len().min(32);
    padded[..pw_len].copy_from_slice(&password[..pw_len]);
    if pw_len < 32 {
        padded[pw_len..].copy_from_slice(&PAD[..32 - pw_len]);
    }

    // Step 2: MD5 of padded || O || P(low32 LE) || ID0 || (EncryptMetadata=false → 0xFFFFFFFF)
    let mut md = Md5::new();
    md.update(padded);
    md.update(&o[..32]);
    md.update(p.to_le_bytes());
    md.update(id0);
    if revision >= 4 && !encrypt_metadata {
        md.update([0xFFu8; 4]);
    }
    let mut digest = md.finalize().to_vec();

    // Step 3 (R>=3): 50 rounds of MD5 on the first /Length-bytes prefix.
    if revision >= 3 {
        for _ in 0..50 {
            let mut m = Md5::new();
            m.update(&digest[..length_bytes.min(digest.len())]);
            digest = m.finalize().to_vec();
        }
    }

    // Step 4: take first /Length-bytes as the file key.
    digest.truncate(length_bytes.min(digest.len()));
    digest
}

/// PDF spec Algorithm 4 (R=2) / Algorithm 5 (R>=3): validate the user
/// password by recomputing /U and comparing.
fn validate_user_password(dec: &Decryptor, u: &[u8], id0: &[u8]) -> bool {
    match dec.revision {
        2 => {
            // Algorithm 4: RC4(file_key, PAD) should equal /U.
            let computed = rc4(&dec.file_key, &PAD);
            constant_eq(&computed, &u[..32])
        }
        _ => {
            // Algorithm 5:
            //   hash = MD5(PAD || ID0)
            //   arc = RC4(file_key, hash)
            //   for i in 1..=19: arc = RC4(file_key XOR i, arc)
            //   /U first 16 bytes == arc first 16 bytes
            let mut md = Md5::new();
            md.update(PAD);
            md.update(id0);
            let mut arc = md.finalize().to_vec();
            arc = rc4(&dec.file_key, &arc);
            for i in 1u8..=19 {
                let mut key = dec.file_key.clone();
                for b in &mut key {
                    *b ^= i;
                }
                arc = rc4(&key, &arc);
            }
            constant_eq(&arc[..16], &u[..16])
        }
    }
}

/// Derive the per-object key (PDF spec §7.6.2 figure 2 + Algorithm 3.1).
///
/// Per the spec, the MD5 input is: file_key || low-3-bytes(obj_num) LE ||
/// low-2-bytes(obj_gen) LE || (AES only) 4-byte "sAlT" salt. Note: obj_num is
/// **3 bytes**, not 4 — common implementations that pass `u32::to_le_bytes`
/// produce a different MD5 input for any obj_num ≥ 256 and fail to decrypt.
fn derive_object_key(file_key: &[u8], obj_num: u32, obj_gen: u16, algorithm: Algorithm) -> Vec<u8> {
    let mut md = Md5::new();
    md.update(file_key);
    let num_le = obj_num.to_le_bytes();
    md.update(&num_le[..3]); // low 3 bytes only
    md.update(obj_gen.to_le_bytes()); // low 2 bytes
    if algorithm == Algorithm::Aes128 {
        // AES adds 4 bytes of salt (the value is documented as 0x73 0x41 0x6C 0x54 = "sAlT").
        md.update([0x73, 0x41, 0x6C, 0x54]);
    }
    let digest = md.finalize();
    // Key length is min(n+5, 16) bytes where n = file_key length.
    let n = (file_key.len() + 5).min(16);
    digest[..n].to_vec()
}

/// RC4 stream cipher (PDF spec §7.6.2). Stateful key schedule, XOR keystream.
fn rc4(key: &[u8], data: &[u8]) -> Vec<u8> {
    if key.is_empty() {
        return data.to_vec();
    }
    // KSA
    let mut s = [0u8; 256];
    for i in 0..256 {
        s[i] = i as u8;
    }
    let mut j: u8 = 0;
    for i in 0..256 {
        j = j.wrapping_add(s[i]).wrapping_add(key[i % key.len()]);
        s.swap(i, j as usize);
    }
    // PRGA
    let mut out = Vec::with_capacity(data.len());
    let mut i: u8 = 0;
    let mut jj: u8 = 0;
    for &b in data {
        i = i.wrapping_add(1);
        jj = jj.wrapping_add(s[i as usize]);
        s.swap(i as usize, jj as usize);
        let k = s[(s[i as usize].wrapping_add(s[jj as usize])) as usize];
        out.push(b ^ k);
    }
    out
}

/// AES-128-CBC decrypt with PKCS#7 unpadding. First 16 bytes of input are the IV.
fn aes_128_cbc_decrypt(key: &[u8], data: &[u8]) -> Vec<u8> {
    use aes::cipher::block_padding::Pkcs7;
    use aes::cipher::{BlockDecryptMut, KeyIvInit};
    use cbc::Decryptor as CbcDec;
    type Aes128CbcDec = CbcDec<aes::Aes128>;

    if data.len() < 16 || !data.len().is_multiple_of(16) {
        // Malformed ciphertext — return raw so callers see recognizable garbage
        // rather than a panic. Real PDFs always align.
        return data.to_vec();
    }
    let (iv, ct) = data.split_at(16);
    if key.len() != 16 {
        // Should not happen with proper file_key length, but guard anyway.
        return data.to_vec();
    }
    let mut buf = ct.to_vec();
    let decryptor = match Aes128CbcDec::new_from_slices(key, iv) {
        Ok(d) => d,
        Err(_) => return data.to_vec(),
    };
    match decryptor.decrypt_padded_mut::<Pkcs7>(&mut buf) {
        Ok(plain) => plain.to_vec(),
        Err(_) => {
            // PKCS#7 unpad failed — sometimes PDFs use padding-less AES for
            // streams. Return the decrypted raw bytes.
            buf
        }
    }
}

/// Constant-time comparison to avoid leaking info about /U via timing.
fn constant_eq(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut diff: u8 = 0;
    for (x, y) in a.iter().zip(b.iter()) {
        diff |= x ^ y;
    }
    diff == 0
}

/// Box::leak a Vec<u8> into a 'static slice. Used to give decrypted bytes
/// the same 'static lifetime that the rest of the parser assumes for cached
/// objects (see Document::leak_pdf_object for the mmap-borrow pattern).
pub fn leak_bytes(b: Vec<u8>) -> &'static [u8] {
    Box::leak(b.into_boxed_slice())
}

/// Recursively decrypt every `String`, `HexString`, and `Stream` body inside
/// a parsed PdfObject tree, using the per-object key derived from
/// (file_key, obj_num, obj_gen). Returns a fully `'static` PdfObject: every
/// borrowed slice (names, dict keys, decrypted bytes) is leaked so the
/// result outlives the mmap lookup.
pub fn decrypt_pdf_object(
    obj: PdfObject<'_>,
    dec: &Decryptor,
    obj_num: u32,
    obj_gen: u16,
) -> PdfObject<'static> {
    match obj {
        PdfObject::String(s) => {
            let plain = dec.decrypt_object(obj_num, obj_gen, s);
            PdfObject::String(leak_bytes(plain))
        }
        PdfObject::HexString(s) => {
            // Decrypt + normalize to a plain String (post-decrypt, the hex
            // distinction is meaningless — it was just an encoding wrapper).
            let plain = dec.decrypt_object(obj_num, obj_gen, s);
            PdfObject::String(leak_bytes(plain))
        }
        PdfObject::Name(n) => PdfObject::Name(leak_bytes(n.to_vec())),
        PdfObject::Stream { dict, data } => {
            let plain = dec.decrypt_object(obj_num, obj_gen, data);
            let new_dict: Vec<(&'static [u8], PdfObject<'static>)> = dict
                .into_iter()
                .map(|(k, v)| {
                    (
                        leak_bytes(k.to_vec()),
                        decrypt_pdf_object(v, dec, obj_num, obj_gen),
                    )
                })
                .collect();
            PdfObject::Stream {
                dict: new_dict,
                data: leak_bytes(plain),
            }
        }
        PdfObject::Dict(d) => {
            let new_d: Vec<(&'static [u8], PdfObject<'static>)> = d
                .into_iter()
                .map(|(k, v)| {
                    (
                        leak_bytes(k.to_vec()),
                        decrypt_pdf_object(v, dec, obj_num, obj_gen),
                    )
                })
                .collect();
            PdfObject::Dict(new_d)
        }
        PdfObject::Array(arr) => PdfObject::Array(
            arr.into_iter()
                .map(|v| decrypt_pdf_object(v, dec, obj_num, obj_gen))
                .collect(),
        ),
        PdfObject::Ref(r) => PdfObject::Ref(r),
        PdfObject::Integer(n) => PdfObject::Integer(n),
        PdfObject::Real(f) => PdfObject::Real(f),
        PdfObject::Bool(b) => PdfObject::Bool(b),
        PdfObject::Null => PdfObject::Null,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rc4_roundtrip() {
        // RFC 6229 test vector: key "Key", plaintext "Plaintext" → BB F3 16 E8 D9 40 AF 0A D3
        let ct = rc4(b"Key", b"Plaintext");
        assert_eq!(
            ct,
            vec![0xBB, 0xF3, 0x16, 0xE8, 0xD9, 0x40, 0xAF, 0x0A, 0xD3]
        );
    }

    #[test]
    fn test_rc4_empty_key_returns_input() {
        let out = rc4(b"", b"hello");
        assert_eq!(out, b"hello");
    }

    #[test]
    fn test_constant_eq_equal() {
        assert!(constant_eq(b"abc", b"abc"));
    }

    #[test]
    fn test_constant_eq_unequal() {
        assert!(!constant_eq(b"abc", b"abd"));
    }

    #[test]
    fn test_constant_eq_different_lengths() {
        assert!(!constant_eq(b"abc", b"abcd"));
    }

    #[test]
    fn test_derive_object_key_rc4_length() {
        // File key of 5 bytes (40-bit RC4) → object key of 5+5 = 10 bytes.
        let key = derive_object_key(&[1, 2, 3, 4, 5], 7, 0, Algorithm::RC4);
        assert_eq!(key.len(), 10);
    }

    #[test]
    fn test_derive_object_key_uses_3_byte_obj_num() {
        // PDF spec §7.6.2: obj_num contributes its low 3 bytes (not 4) to
        // the per-object key MD5. This is the most common bug-source in PDF
        // crypto impls — using u32::to_le_bytes() shifts the gen salt by one
        // byte and produces a different key. Verify by comparing against a
        // hand-computed reference value.
        //
        // Reference inputs (file_key, obj_num=256, obj_gen=0):
        //   spec-correct: file_key || 00 01 00 || 00 00  → 5+3+2 = 10 bytes
        //   buggy (u32):  file_key || 00 01 00 00 || 00 00 → 5+4+2 = 11 bytes
        // The two MD5 inputs differ → different obj keys → different RC4
        // keystream. We pin the spec-correct output here so any future
        // regression that re-introduces the 4-byte form will fail loudly.
        let key_correct = derive_object_key(&[0xAA; 5], 256, 0, Algorithm::RC4);
        // Independent reference computed in Python with the 3-byte form:
        //   hashlib.md5(b'\xaa'*5 + (256).to_bytes(3,'little') + (0).to_bytes(2,'little'))
        //     .digest()[:10]
        let expected: [u8; 10] = [0xbb, 0xd6, 0xcb, 0x1c, 0x1a, 0xc3, 0xe9, 0x97, 0xf5, 0x59];
        assert_eq!(&key_correct[..], &expected[..]);
    }

    #[test]
    fn test_derive_object_key_aes_has_salt() {
        // AES object key adds 4 salt bytes during MD5; result capped at 16.
        let key = derive_object_key(
            &[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
            1,
            0,
            Algorithm::Aes128,
        );
        assert_eq!(key.len(), 16);
    }

    #[test]
    fn test_pad_constant_is_32_bytes() {
        assert_eq!(PAD.len(), 32);
    }

    #[test]
    fn test_unsupported_aes256_returns_error() {
        let dict = PdfObject::Dict(vec![
            (b"Filter" as &[u8], PdfObject::Name(b"Standard")),
            (b"V", PdfObject::Integer(5)),
            (b"R", PdfObject::Integer(6)),
        ]);
        let result = Decryptor::from_encrypt_dict(&dict, b"");
        assert!(result.is_err());
        let msg = format!("{}", result.unwrap_err());
        assert!(msg.contains("AES-256"));
    }

    #[test]
    fn test_unsupported_filter_returns_error() {
        let dict = PdfObject::Dict(vec![
            (b"Filter" as &[u8], PdfObject::Name(b"Azure")),
            (b"V", PdfObject::Integer(1)),
            (b"R", PdfObject::Integer(2)),
        ]);
        let result = Decryptor::from_encrypt_dict(&dict, b"");
        assert!(result.is_err());
    }

    #[test]
    fn test_get_padded_bytes_handles_strings() {
        let s = PdfObject::String(b"short");
        let v = get_padded_bytes(Some(&s), 32);
        assert_eq!(v.len(), 32);
        assert_eq!(&v[..5], b"short");
    }

    #[test]
    fn test_get_padded_bytes_handles_missing() {
        let v = get_padded_bytes(None, 32);
        assert_eq!(v.len(), 32);
        assert!(v.iter().all(|&b| b == 0));
    }
}
