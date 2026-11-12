"""Safe, explicit lineage projection. Only selected event fields enter the ledger."""
from .devices import Lineage
from .events import Event


OPERATIONS = {
    "public_key_retrieved":"Published recipient key",
    "reply_key_encapsulated":"Unverified reply key (encrypted)",
    "message_encrypted":"Encrypted bundle",
    "message_chunked":"Encrypted chunks",
    "fragment_stored":"Encrypted fragment",
    "manifest_published":"Encrypted manifest",
    "manifest_retrieved":"Encrypted manifest",
    "fragment_retrieved":"Encrypted fragment",
    "message_reconstructed":"Encrypted bundle",
    "message_decrypted":"Device plaintext",
    "reply_key_learned":"Unverified reply key",
}


def project(event: Event) -> Lineage | None:
    if event.event_type not in OPERATIONS or not event.message_id:
        return None
    payload=event.payload
    artefact=str(payload.get("fragment_id") or payload.get("artefact_id") or event.message_id)
    location=(event.target_id if event.event_type=="fragment_stored" else event.source_id) or ""
    return Lineage(simulation_time_ms=event.simulation_time_ms,message_id=event.message_id,
                   operation=event.event_type,location=location,artefact=artefact,
                   container=payload.get("container"),detail=OPERATIONS[event.event_type])
