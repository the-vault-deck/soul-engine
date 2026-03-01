import uuid
import nacl.signing
import nacl.encoding
import hashlib
import json
from datetime import datetime, timezone


class Soul:

    def __init__(self, promotion_threshold=3):
        self.soul_id = str(uuid.uuid4())

        # Identity
        self.signing_key = nacl.signing.SigningKey.generate()
        self.verify_key = self.signing_key.verify_key
        self.public_key = self.verify_key.encode(
            encoder=nacl.encoding.HexEncoder
        ).decode()

        # Memory Structures
        self.append_log = []
        self.hot_memory = {}
        self.candidates = {}
        self.promotion_threshold = promotion_threshold

        self._create_genesis_block()

    # =========================
    # CRYPTO HELPERS
    # =========================

    def _hash_payload(self, payload: dict) -> str:
        encoded = json.dumps(payload, sort_keys=True).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _sign_entry(self, entry_hash: str) -> str:
        signed = self.signing_key.sign(entry_hash.encode())
        return signed.signature.hex()

    # =========================
    # GENESIS
    # =========================

    def _create_genesis_block(self):
        payload = {
            "event": "SOUL_CREATED",
            "soul_id": self.soul_id
        }

        payload_hash = self._hash_payload(payload)

        entry = {
            "entry_id": payload_hash,
            "entry_type": "GENESIS",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
            "payload_hash": payload_hash,
            "previous_entry_hash": "0",
            "signature": self._sign_entry(payload_hash)
        }

        self.append_log.append(entry)

    # =========================
    # APPEND
    # =========================

    def append_entry(self, payload: dict, entry_type: str = "MEMORY"):
        last_entry = self.append_log[-1]
        payload_hash = self._hash_payload(payload)

        entry = {
            "entry_id": payload_hash,
            "entry_type": entry_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
            "payload_hash": payload_hash,
            "previous_entry_hash": last_entry["entry_id"],
            "signature": self._sign_entry(payload_hash)
        }

        self.append_log.append(entry)

    # =========================
    # VERIFY
    # =========================

    def verify_chain(self) -> bool:
        verify_key = nacl.signing.VerifyKey(
            self.public_key, encoder=nacl.encoding.HexEncoder
        )

        for i, entry in enumerate(self.append_log):
            if i == 0:
                if entry["previous_entry_hash"] != "0":
                    return False
            else:
                if entry["previous_entry_hash"] != self.append_log[i-1]["entry_id"]:
                    return False

            expected_hash = self._hash_payload(entry["payload"])
            if expected_hash != entry["payload_hash"]:
                return False

            try:
                verify_key.verify(
                    entry["payload_hash"].encode(),
                    bytes.fromhex(entry["signature"])
                )
            except Exception:
                return False

        return True

    # =========================
    # PROMOTION SYSTEM
    # =========================

    def flag_candidate(self, key, value):
        if key not in self.candidates:
            self.candidates[key] = {
                "value": value,
                "count": 1
            }
        else:
            self.candidates[key]["count"] += 1

        if self.candidates[key]["count"] >= self.promotion_threshold:
            if key not in self.hot_memory:
                self.hot_memory[key] = self.candidates[key]["value"]

                self.append_entry(
                    {"key": key, "value": self.hot_memory[key]},
                    entry_type="PROMOTION"
                )

                print(f"{key} auto-promoted to HOT memory.")

    # =========================
    # PERSISTENCE
    # =========================

    def save_to_disk(self, filename):
        data = {
            "soul_id": self.soul_id,
            "public_key": self.public_key,
            "append_log": self.append_log,
            "promotion_threshold": self.promotion_threshold
        }

        with open(filename, "w") as f:
            json.dump(data, f, indent=2)

        print(f"Soul saved to {filename}")

    @classmethod
    def load_from_disk(cls, filename):
        with open(filename, "r") as f:
            data = json.load(f)

        soul = cls(promotion_threshold=data["promotion_threshold"])

        soul.soul_id = data["soul_id"]
        soul.public_key = data["public_key"]
        soul.append_log = data["append_log"]

        soul.rebuild_hot_memory_from_chain()

        print(f"Soul loaded from {filename}")

        return soul

    # =========================
    # REPLAY
    # =========================

    def rebuild_hot_memory_from_chain(self):
        self.hot_memory = {}

        for entry in self.append_log:
            if entry["entry_type"] == "PROMOTION":
                key = entry["payload"]["key"]
                value = entry["payload"]["value"]
                self.hot_memory[key] = value

        print("HOT MEMORY REBUILT:", self.hot_memory)

if __name__ == "__main__":

    # Create Soul
    soul = Soul(promotion_threshold=3)

    soul.flag_candidate("USER_PREF:TONE", "CONCISE")
    soul.flag_candidate("USER_PREF:TONE", "CONCISE")
    soul.flag_candidate("USER_PREF:TONE", "CONCISE")

    print("CHAIN VALID BEFORE SAVE:", soul.verify_chain())

    soul.save_to_disk("atlas_soul.json")

    print("\n--- SIMULATING FULL RESTART ---\n")

    loaded_soul = Soul.load_from_disk("atlas_soul.json")

    print("CHAIN VALID AFTER LOAD:", loaded_soul.verify_chain())