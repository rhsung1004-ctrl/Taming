using System.Collections.Generic;
using UnityEngine;

public static class Util
{
    static Material baseMat;
    static readonly Dictionary<Color, Material> cache = new Dictionary<Color, Material>();
    static readonly Dictionary<Color, Material> glowCache = new Dictionary<Color, Material>();

    public static void ResetCaches()
    {
        baseMat = null;
        cache.Clear();
        glowCache.Clear();
    }

    // 현재 렌더 파이프라인(URP/Built-in)의 기본 머티리얼을 복제해서 쓴다 → 분홍색 깨짐 방지
    static Material BaseMat()
    {
        if (baseMat == null)
        {
            var tmp = GameObject.CreatePrimitive(PrimitiveType.Cube);
            baseMat = tmp.GetComponent<Renderer>().sharedMaterial;
            Object.DestroyImmediate(tmp);
        }
        return baseMat;
    }

    public static Material NewMat(Color c)
    {
        var m = new Material(BaseMat());
        m.color = c;
        if (m.HasProperty("_Smoothness")) m.SetFloat("_Smoothness", 0.12f);
        if (m.HasProperty("_Glossiness")) m.SetFloat("_Glossiness", 0.12f);
        return m;
    }

    public static Material Mat(Color c)
    {
        Material m;
        if (!cache.TryGetValue(c, out m) || m == null)
        {
            m = NewMat(c);
            cache[c] = m;
        }
        return m;
    }

    public static Material Glow(Color c)
    {
        Material m;
        if (!glowCache.TryGetValue(c, out m) || m == null)
        {
            m = NewMat(c);
            m.EnableKeyword("_EMISSION");
            if (m.HasProperty("_EmissionColor")) m.SetColor("_EmissionColor", c * 2f);
            m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.RealtimeEmissive;
            glowCache[c] = m;
        }
        return m;
    }

    // 콜라이더 없는 장식용 도형
    public static Transform Part(PrimitiveType type, Transform parent, Vector3 pos, Vector3 scale, Color color,
                                 Vector3 euler = default(Vector3), bool glow = false)
    {
        var g = GameObject.CreatePrimitive(type);
        Object.DestroyImmediate(g.GetComponent<Collider>());
        g.layer = 2;
        if (parent != null) g.transform.SetParent(parent, false);
        g.transform.localPosition = pos;
        g.transform.localEulerAngles = euler;
        g.transform.localScale = scale;
        g.GetComponent<Renderer>().sharedMaterial = glow ? Glow(color) : Mat(color);
        return g.transform;
    }

    public static Transform Pivot(Transform parent, Vector3 pos)
    {
        var t = new GameObject("pivot").transform;
        t.SetParent(parent, false);
        t.localPosition = pos;
        return t;
    }

    public static Vector3 Flat(Vector3 v)
    {
        v.y = 0f;
        return v;
    }

    public static Color WithA(Color c, float a)
    {
        c.a = a;
        return c;
    }

    // 한국어 조사 처리
    public static bool HasBatchim(string s)
    {
        if (string.IsNullOrEmpty(s)) return false;
        char c = s[s.Length - 1];
        if (c < 0xAC00 || c > 0xD7A3) return false;
        return (c - 0xAC00) % 28 != 0;
    }
    public static string IGa(string s) { return s + (HasBatchim(s) ? "이" : "가"); }
    public static string EulReul(string s) { return s + (HasBatchim(s) ? "을" : "를"); }
    public static string EunNeun(string s) { return s + (HasBatchim(s) ? "은" : "는"); }

    public static Texture2D Circle(int size, bool ring)
    {
        var t = new Texture2D(size, size, TextureFormat.RGBA32, false);
        t.wrapMode = TextureWrapMode.Clamp;
        t.filterMode = FilterMode.Bilinear;
        var px = new Color32[size * size];
        float r = size * 0.5f - 1f;
        Vector2 c = new Vector2(size * 0.5f, size * 0.5f);
        for (int y = 0; y < size; y++)
        {
            for (int x = 0; x < size; x++)
            {
                float d = (new Vector2(x + 0.5f, y + 0.5f) - c).magnitude;
                float a = ring ? Mathf.Clamp01(1f - Mathf.Abs(d - (r - 3f)) / 2.5f) : Mathf.Clamp01(r - d);
                px[y * size + x] = new Color32(255, 255, 255, (byte)(a * 255f));
            }
        }
        t.SetPixels32(px);
        t.Apply();
        return t;
    }
}
