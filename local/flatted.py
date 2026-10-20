"""Parser del formato flatted que usa n8n para guardar las ejecuciones."""
import json

def cargar(texto):
    arr = json.loads(texto) if isinstance(texto, str) else texto
    hechos = {}
    def rec(i):
        if i in hechos: return hechos[i]
        v = arr[i]
        if isinstance(v, list):
            out = []; hechos[i] = out
            for x in v: out.append(val(x))
            return out
        if isinstance(v, dict):
            out = {}; hechos[i] = out
            for k, x in v.items(): out[k] = val(x)
            return out
        hechos[i] = v
        return v
    def val(x):
        if isinstance(x, str):
            try: return rec(int(x))
            except (ValueError, IndexError): return x
        return x
    return rec(0)
