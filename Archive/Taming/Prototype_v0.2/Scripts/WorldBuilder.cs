using System.Collections.Generic;
using UnityEngine;

// 코드로 섬(오픈월드 테스트 맵)을 생성한다.
//  - 남쪽 초원(시작 지점): 슬라임, 불여우, 깃털 새
//  - 서쪽 숲: 들늑대 / 동쪽 붉은 언덕: 불꽃 도마뱀
//  - 북서쪽 큰 산
//  - 북동쪽 바위 기둥 꼭대기(23m): 그리폰 둥지 → 깃털 새(최고 26m)로 겨우 닿는 높이
//  - 남서쪽 하늘 섬(55m): 그리폰(최고 75m)이 있어야 갈 수 있음
public static class WorldBuilder
{
    public const float Size = 480f;
    const int Res = 161;
    const int GroundMask = ~(1 << 2);

    public static readonly Vector2 NestXZ = new Vector2(85f, 115f);
    public static readonly Vector2 SkyXZ = new Vector2(-115f, -140f);
    public const float NestHeight = 23f;
    public const float SkyHeight = 55f;

    public static Vector3 SpawnPoint, NestTop, SkyTop;

    static readonly Color Grass = new Color(0.47f, 0.74f, 0.33f);
    static readonly Color Rock = new Color(0.55f, 0.51f, 0.47f);

    static float G(float x, float z, float cx, float cz, float r)
    {
        float dx = x - cx, dz = z - cz;
        return Mathf.Exp(-(dx * dx + dz * dz) / (r * r));
    }

    public static float Height(float x, float z)
    {
        float r = Mathf.Sqrt(x * x + z * z) + (Mathf.PerlinNoise(x * 0.008f + 300f, z * 0.008f + 300f) - 0.5f) * 50f;
        float edge = Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(232f, 165f, r));
        float n = Mathf.PerlinNoise(x * 0.011f + 37f, z * 0.011f + 91f);
        float n2 = Mathf.PerlinNoise(x * 0.045f + 11f, z * 0.045f + 5f);
        float land = 2.5f + n * 9f + n2 * 1.2f;
        land = Mathf.Lerp(land, 4f, G(x, z, 0f, -65f, 55f) * 0.85f);   // 평평한 시작 초원
        land += 34f * G(x, z, -55f, 125f, 50f);                          // 북서쪽 산
        land += 10f * G(x, z, 135f, 15f, 40f);                           // 동쪽 언덕
        return Mathf.Lerp(-6f, land, edge);
    }

    public static float GroundY(float x, float fromY, float z)
    {
        RaycastHit hit;
        if (Physics.Raycast(new Vector3(x, fromY, z), Vector3.down, out hit, 400f, GroundMask, QueryTriggerInteraction.Ignore))
            return hit.point.y;
        return Height(x, z);
    }

    public static void Build()
    {
        SpawnPoint = new Vector3(0f, Height(0f, -65f) + 1.2f, -65f);
        BuildTerrain();
        BuildWater();
        BuildPillar();
        BuildSkyIsland();
        BuildTrees();
        BuildRocks();
        BuildClouds();
        BuildCamp();
        Physics.SyncTransforms();
    }

    static void BuildTerrain()
    {
        var verts = new Vector3[Res * Res];
        var uvs = new Vector2[Res * Res];
        float step = Size / (Res - 1);
        float half = Size * 0.5f;
        for (int z = 0; z < Res; z++)
        {
            for (int x = 0; x < Res; x++)
            {
                float wx = -half + x * step, wz = -half + z * step;
                int i = z * Res + x;
                verts[i] = new Vector3(wx, Height(wx, wz), wz);
                uvs[i] = new Vector2((float)x / (Res - 1), (float)z / (Res - 1));
            }
        }
        var tris = new int[(Res - 1) * (Res - 1) * 6];
        int t = 0;
        for (int z = 0; z < Res - 1; z++)
        {
            for (int x = 0; x < Res - 1; x++)
            {
                int i = z * Res + x;
                tris[t++] = i; tris[t++] = i + Res; tris[t++] = i + 1;
                tris[t++] = i + 1; tris[t++] = i + Res; tris[t++] = i + Res + 1;
            }
        }
        var mesh = new Mesh();
        mesh.indexFormat = UnityEngine.Rendering.IndexFormat.UInt32;
        mesh.vertices = verts;
        mesh.uv = uvs;
        mesh.triangles = tris;
        mesh.RecalculateNormals();
        mesh.RecalculateBounds();

        var g = new GameObject("Terrain");
        g.AddComponent<MeshFilter>().sharedMesh = mesh;
        var mat = Util.NewMat(Color.white);
        mat.mainTexture = BuildTexture();
        g.AddComponent<MeshRenderer>().sharedMaterial = mat;
        g.AddComponent<MeshCollider>().sharedMesh = mesh;
    }

    static Texture2D BuildTexture()
    {
        const int T = 384;
        var tex = new Texture2D(T, T, TextureFormat.RGB24, true);
        var px = new Color32[T * T];
        float half = Size * 0.5f;
        Color sand = new Color(0.87f, 0.8f, 0.58f);
        Color forest = new Color(0.24f, 0.47f, 0.22f);
        Color volcanic = new Color(0.55f, 0.34f, 0.26f);
        Color snow = new Color(0.95f, 0.96f, 0.98f);
        Color seabed = new Color(0.55f, 0.58f, 0.5f);
        for (int y = 0; y < T; y++)
        {
            for (int x = 0; x < T; x++)
            {
                float wx = -half + (x + 0.5f) / T * Size, wz = -half + (y + 0.5f) / T * Size;
                float h = Height(wx, wz);
                float hx = Height(wx + 1.5f, wz) - h, hz = Height(wx, wz + 1.5f) - h;
                float slope = Mathf.Sqrt(hx * hx + hz * hz) / 1.5f;
                Color c = Color.Lerp(Grass, forest, G(wx, wz, -130f, 0f, 95f) * 1.1f);
                c = Color.Lerp(c, volcanic, G(wx, wz, 135f, 15f, 70f));
                float v = Mathf.PerlinNoise(wx * 0.15f, wz * 0.15f) * 0.12f - 0.06f;
                c = new Color(c.r + v, c.g + v, c.b + v * 0.5f);
                if (h < 1.2f) c = Color.Lerp(sand, c, Mathf.InverseLerp(0.4f, 1.2f, h));
                if (h < 0f) c = Color.Lerp(sand, seabed, Mathf.InverseLerp(0f, -4f, h));
                c = Color.Lerp(c, Rock, Mathf.InverseLerp(0.55f, 0.9f, slope));
                if (h > 28f) c = Color.Lerp(c, Rock, Mathf.InverseLerp(28f, 32f, h));
                if (h > 36f) c = Color.Lerp(c, snow, Mathf.InverseLerp(36f, 39f, h));
                px[y * T + x] = c;
            }
        }
        tex.SetPixels32(px);
        tex.Apply(true);
        tex.wrapMode = TextureWrapMode.Clamp;
        tex.filterMode = FilterMode.Bilinear;
        tex.anisoLevel = 4;
        return tex;
    }

    static void BuildWater()
    {
        var w = GameObject.CreatePrimitive(PrimitiveType.Plane);
        Object.DestroyImmediate(w.GetComponent<Collider>());
        w.name = "Sea";
        w.transform.position = new Vector3(0f, 0.05f, 0f);
        w.transform.localScale = new Vector3(120f, 1f, 120f);
        var m = Util.NewMat(new Color(0.22f, 0.55f, 0.85f));
        if (m.HasProperty("_Smoothness")) m.SetFloat("_Smoothness", 0.85f);
        if (m.HasProperty("_Glossiness")) m.SetFloat("_Glossiness", 0.85f);
        w.GetComponent<Renderer>().sharedMaterial = m;
    }

    // 밟을 수 있는 도형 (원기둥·구는 MeshCollider로 바꿔야 늘린 모양대로 충돌함)
    static GameObject Solid(PrimitiveType t, Vector3 pos, Vector3 scale, Color c)
    {
        var g = GameObject.CreatePrimitive(t);
        g.transform.position = pos;
        g.transform.localScale = scale;
        if (t != PrimitiveType.Cube)
        {
            Object.DestroyImmediate(g.GetComponent<Collider>());
            g.AddComponent<MeshCollider>().sharedMesh = g.GetComponent<MeshFilter>().sharedMesh;
        }
        g.GetComponent<Renderer>().sharedMaterial = Util.Mat(c);
        return g;
    }

    static void BuildPillar()
    {
        float x = NestXZ.x, z = NestXZ.y;
        float baseY = Height(x, z) - 3f;
        float h = NestHeight - baseY;
        Solid(PrimitiveType.Cylinder, new Vector3(x, baseY + h * 0.5f, z), new Vector3(16f, h * 0.5f, 16f), Rock);
        Solid(PrimitiveType.Cylinder, new Vector3(x, NestHeight + 0.05f, z), new Vector3(16.4f, 0.15f, 16.4f), Grass);
        // 기둥 겉면 바위 장식
        for (int i = 0; i < 10; i++)
        {
            float a = i * Mathf.PI * 2f / 10f;
            float yy = baseY + 3f + (i % 4) * (h - 6f) / 4f;
            Util.Part(PrimitiveType.Cube, null, new Vector3(x + Mathf.Cos(a) * 7.8f, yy, z + Mathf.Sin(a) * 7.8f),
                      new Vector3(2.4f, 1.6f, 2.2f), new Color(0.48f, 0.45f, 0.42f), new Vector3(10f * i, 37f * i, 5f));
        }
        // 둥지
        float top = NestHeight + 0.2f;
        Color twig = new Color(0.5f, 0.36f, 0.22f);
        for (int i = 0; i < 16; i++)
        {
            float a = i * Mathf.PI * 2f / 16f;
            Util.Part(PrimitiveType.Cube, null, new Vector3(x + Mathf.Cos(a) * 3.6f, top + 0.35f, z + Mathf.Sin(a) * 3.6f),
                      new Vector3(1.8f, 0.35f, 0.4f), twig, new Vector3(0f, -a * Mathf.Rad2Deg + 90f, 15f));
        }
        for (int i = 0; i < 3; i++)
            Util.Part(PrimitiveType.Sphere, null, new Vector3(x - 0.6f + i * 0.6f, top + 0.35f, z - 1.2f + (i % 2) * 0.4f),
                      new Vector3(0.45f, 0.6f, 0.45f), new Color(0.95f, 0.92f, 0.8f));
        NestTop = new Vector3(x, top, z);
    }

    static void BuildSkyIsland()
    {
        float x = SkyXZ.x, z = SkyXZ.y, top = SkyHeight;
        Color earth = new Color(0.5f, 0.38f, 0.28f);
        Solid(PrimitiveType.Sphere, new Vector3(x, top - 7f, z), new Vector3(46f, 14f, 46f), earth);
        Solid(PrimitiveType.Cylinder, new Vector3(x, top, z), new Vector3(42f, 0.6f, 42f), Grass);
        for (int i = 0; i < 7; i++)
        {
            float a = i * 0.9f;
            Util.Part(PrimitiveType.Cube, null, new Vector3(x + Mathf.Cos(a) * 9f, top - 15f - (i % 3) * 3f, z + Mathf.Sin(a) * 9f),
                      new Vector3(4f, 7f, 4f), Rock, new Vector3(i * 13f, i * 29f, i * 7f));
        }
        // 폭포
        Util.Part(PrimitiveType.Cube, null, new Vector3(x + 21f, top - 25f, z), new Vector3(3f, 50f, 1.5f),
                  new Color(0.6f, 0.85f, 1f), default(Vector3), true);
        var rnd = new System.Random(3);
        for (int i = 0; i < 6; i++)
        {
            float a = (float)rnd.NextDouble() * Mathf.PI * 2f, d = 8f + (float)rnd.NextDouble() * 9f;
            Tree(new Vector3(x + Mathf.Cos(a) * d, top + 0.6f, z + Mathf.Sin(a) * d), 1f, false, rnd.Next());
        }
        // 보물 상자
        float y = top + 0.6f;
        Color gold = new Color(1f, 0.8f, 0.25f);
        Util.Part(PrimitiveType.Cube, null, new Vector3(x, y + 0.45f, z), new Vector3(1.6f, 0.9f, 1.1f), new Color(0.55f, 0.32f, 0.18f));
        Util.Part(PrimitiveType.Cube, null, new Vector3(x, y + 1f, z), new Vector3(1.7f, 0.25f, 1.2f), gold, default(Vector3), true);
        var lg = new GameObject("ChestLight");
        lg.transform.position = new Vector3(x, y + 2.5f, z);
        var l = lg.AddComponent<Light>();
        l.type = LightType.Point;
        l.color = gold;
        l.range = 14f;
        l.intensity = 3f;
        SkyTop = new Vector3(x, y, z);
    }

    static void BuildTrees()
    {
        var rnd = new System.Random(7);
        int placed = 0;
        for (int i = 0; i < 3000 && placed < 260; i++)
        {
            float x = (float)(rnd.NextDouble() * 2 - 1) * 220f;
            float z = (float)(rnd.NextDouble() * 2 - 1) * 220f;
            float h = Height(x, z);
            if (h < 1.5f || h > 26f) continue;
            if (G(x, z, 0f, -65f, 30f) > 0.4f) continue;                       // 시작 지점은 비움
            if ((new Vector2(x, z) - NestXZ).magnitude < 12f) continue;
            if (Mathf.Abs(Height(x + 2f, z) - h) > 2.5f) continue;              // 급경사 제외
            float forest = G(x, z, -130f, 0f, 95f);
            if (rnd.NextDouble() > 0.06 + forest * 0.9) continue;
            Tree(new Vector3(x, h, z), 0.8f + (float)rnd.NextDouble() * 0.7f, forest > 0.4f, rnd.Next());
            placed++;
        }
    }

    static void Tree(Vector3 p, float s, bool pine, int seed)
    {
        var root = new GameObject("Tree");
        root.layer = 2;
        root.transform.position = p;
        Transform tr = root.transform;
        var lib = ModelLibrary.I;
        if (lib != null && lib.trees.Count > 0)
        {
            var prefab = lib.trees[seed % lib.trees.Count];
            ModelLibrary.Spawn(prefab, tr, 6f * s, seed % 360);
        }
        else
        {
            PrimitiveTree(tr, s, pine);
        }
        var col = root.AddComponent<CapsuleCollider>();
        col.center = new Vector3(0f, 1.5f * s, 0f);
        col.radius = 0.35f * s;
        col.height = 3f * s;
    }

    static void PrimitiveTree(Transform tr, float s, bool pine)
    {
        Util.Part(PrimitiveType.Cylinder, tr, new Vector3(0f, 1.6f * s, 0f), new Vector3(0.45f * s, 1.6f * s, 0.45f * s), new Color(0.45f, 0.3f, 0.2f));
        if (pine)
        {
            Color c = new Color(0.17f, 0.4f, 0.22f);
            Util.Part(PrimitiveType.Sphere, tr, new Vector3(0f, 3.0f * s, 0f), new Vector3(2.8f, 1.5f, 2.8f) * s, c);
            Util.Part(PrimitiveType.Sphere, tr, new Vector3(0f, 4.1f * s, 0f), new Vector3(2.1f, 1.3f, 2.1f) * s, c);
            Util.Part(PrimitiveType.Sphere, tr, new Vector3(0f, 5.0f * s, 0f), new Vector3(1.3f, 1.1f, 1.3f) * s, c);
        }
        else
        {
            Color c = new Color(0.33f, 0.62f, 0.27f);
            Util.Part(PrimitiveType.Sphere, tr, new Vector3(0f, 4.0f * s, 0f), new Vector3(3.2f, 2.8f, 3.2f) * s, c);
            Util.Part(PrimitiveType.Sphere, tr, new Vector3(0.8f * s, 3.4f * s, 0.5f * s), new Vector3(2.2f, 2f, 2.2f) * s, c);
        }
    }

    static void BuildRocks()
    {
        var rnd = new System.Random(11);
        int placed = 0;
        for (int i = 0; i < 800 && placed < 70; i++)
        {
            float x = (float)(rnd.NextDouble() * 2 - 1) * 210f;
            float z = (float)(rnd.NextDouble() * 2 - 1) * 210f;
            float h = Height(x, z);
            if (h < 1f || G(x, z, 0f, -65f, 25f) > 0.4f) continue;
            float volcanic = G(x, z, 135f, 15f, 60f);
            if (rnd.NextDouble() > 0.15 + volcanic) continue;
            float s = 0.8f + (float)rnd.NextDouble() * 1.8f;
            Color c = volcanic > 0.3f ? new Color(0.3f, 0.24f, 0.22f) : Rock;
            var lib = ModelLibrary.I;
            if (lib != null && lib.rocks.Count > 0)
            {
                var root = new GameObject("Rock");
                root.transform.position = new Vector3(x, h - 0.2f, z);
                ModelLibrary.Spawn(lib.rocks[rnd.Next(lib.rocks.Count)], root.transform, s * 1.3f, (float)rnd.NextDouble() * 360f);
                Bounds b;
                if (ModelLibrary.MeasureBounds(root, out b))
                {
                    var box = root.AddComponent<BoxCollider>();
                    box.center = b.center - root.transform.position;
                    box.size = b.size * 0.9f;
                }
                placed++;
                continue;
            }
            var g = Solid(PrimitiveType.Sphere, new Vector3(x, h + s * 0.2f, z), new Vector3(s * 1.4f, s, s * 1.2f), c);
            g.transform.rotation = Quaternion.Euler(0f, (float)rnd.NextDouble() * 360f, 0f);
            placed++;
        }
    }

    static void BuildClouds()
    {
        var rnd = new System.Random(5);
        Color c = new Color(1f, 1f, 1f);
        for (int i = 0; i < 28; i++)
        {
            float x = (float)(rnd.NextDouble() * 2 - 1) * 230f;
            float z = (float)(rnd.NextDouble() * 2 - 1) * 230f;
            float y = 36f + (float)rnd.NextDouble() * 14f;
            var root = new GameObject("Cloud").transform;
            root.position = new Vector3(x, y, z);
            for (int k = 0; k < 3; k++)
                Util.Part(PrimitiveType.Sphere, root, new Vector3(k * 4f - 4f, (k == 1) ? 1.2f : 0f, (float)rnd.NextDouble() * 2f),
                          new Vector3(7f, 3f, 5f), c);
        }
    }

    static void BuildCamp()
    {
        // 계약 석상 (부활 지점)
        Vector3 p = new Vector3(0f, Height(0f, -57f), -57f);
        var b = GameObject.CreatePrimitive(PrimitiveType.Cube);
        b.transform.position = p + Vector3.up * 0.3f;
        b.transform.localScale = new Vector3(2.4f, 0.6f, 2.4f);
        b.GetComponent<Renderer>().sharedMaterial = Util.Mat(new Color(0.75f, 0.73f, 0.7f));
        Solid(PrimitiveType.Cylinder, p + Vector3.up * 1.6f, new Vector3(0.7f, 1f, 0.7f), new Color(0.82f, 0.8f, 0.76f));
        Util.Part(PrimitiveType.Sphere, null, p + Vector3.up * 3.3f, Vector3.one * 0.8f, new Color(0.55f, 0.9f, 1f), default(Vector3), true);
        var lg = new GameObject("StatueLight");
        lg.transform.position = p + Vector3.up * 3.5f;
        var l = lg.AddComponent<Light>();
        l.type = LightType.Point;
        l.color = new Color(0.55f, 0.9f, 1f);
        l.range = 10f;
        l.intensity = 2f;
    }
}

public class Spawner : MonoBehaviour
{
    public string speciesId;
    public float radius;
    public int count;
    public int minLv = 1, maxLv = 1;
    public float respawn = 20f;
    readonly List<Monster> alive = new List<Monster>();
    float timer;

    public static Spawner Create(string id, Vector3 center, float radius, int count, int minLv, int maxLv, float respawn)
    {
        var g = new GameObject("Spawner_" + id);
        g.transform.position = center;
        var s = g.AddComponent<Spawner>();
        s.speciesId = id;
        s.radius = radius;
        s.count = count;
        s.minLv = minLv;
        s.maxLv = maxLv;
        s.respawn = respawn;
        s.timer = respawn;
        for (int i = 0; i < count; i++) s.SpawnOne();
        return s;
    }

    void Update()
    {
        alive.RemoveAll(m => m == null);
        if (alive.Count < count)
        {
            timer -= Time.deltaTime;
            if (timer <= 0f)
            {
                SpawnOne();
                timer = respawn;
            }
        }
        else timer = respawn;
    }

    void SpawnOne()
    {
        var d = GameDB.Get(speciesId);
        for (int tries = 0; tries < 15; tries++)
        {
            Vector2 r = Random.insideUnitCircle * radius;
            Vector3 p = transform.position + new Vector3(r.x, 0f, r.y);
            p.y = WorldBuilder.GroundY(p.x, 250f, p.z);
            if (p.y < 0.8f) continue;
            var m = Monster.Create(d, Random.Range(minLv, maxLv + 1), p, null);
            m.spawner = this;
            m.wanderRadius = Mathf.Clamp(radius * 0.4f, 2f, 10f);
            alive.Add(m);
            return;
        }
    }

    public void OnRemoved(Monster m)
    {
        alive.Remove(m);
    }
}
