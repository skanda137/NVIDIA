"""Run this on YOUR machine (the cloud sandbox cannot reach Nebius):
    export TOKEN_FACTORY_API_KEY=...        # never commit or paste this anywhere
    python list_models.py
Prints the Nemotron models your key can use and the tier each would be assigned."""
import generator as g

ids = [m.id for m in g._client().models.list()]
print(f"{len(ids)} models available")
print("Nemotron models:", *[i for i in ids if "nemotron" in i.lower()], sep="\n  ")
print("Tier assignment (override with NEMOTRON_NANO_MODEL / _SUPER_ / _ULTRA_):")
for tier, mid in g.discover_tier_models(ids).items():
    print(f"  {tier:15s} -> {mid}")
