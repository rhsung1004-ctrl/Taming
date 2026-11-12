using System.Collections.Generic;
using UnityEngine;

namespace Necro.Proto
{
    // 코드로 만드는 테스트 필드 (약 480m 섬).
    //  남쪽  버려진 묘지 — 시작 지점, 해골 병사·늑대·해골 궁수
    //  중앙  납골당 — 묘지기 (영웅)
    //  동쪽  잿빛 폐허 — 망령 기사 (정예)
    //  북동  용의 무덤 — 잠들지 못한 고룡 (보스) → 지배하면 본드래곤
    //  남서 하늘  부유 성채 — 본드래곤으로만 갈 수 있는 마지막 목표
    public static class World
    {
        public const float Size = 480f;
        const int Res = 161;

        public static readonly Vector2 StartXZ = new Vector2(0f, -65f);
        public static readonly Vector2 CryptXZ = new Vector2(-12f, 32f);
        public static readonly Vector2 RuinsXZ = new Vector2(130f, 12f);
        public static readonly Vector2 RoostXZ = new Vector2(85f, 115f);
        public static readonly Vector2 SkyXZ = new Vector2(-115f, -140f);
        public const float SkyHeight = 55f;
        public const float SkyRadius = 20f;

        public static Vector3 SpawnPoint, SkyTop;

        static readonly Color Rock = new Color(0.36f, 0.34f, 0.36f);

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
            land = Mathf.Lerp(land, 4f, G(x, z, StartXZ.x, StartXZ.y, 55f) * 0.85f);     // 평평한 묘지
            land = Mathf.Lerp(land, 6f, G(x, z, CryptXZ.x, CryptXZ.y, 26f) * 0.9f);      // 납골당 앞마당
            land += 34f * G(x, z, -70f, 135f, 48f);                                       // 북서쪽 산
            land = Mathf.Lerp(land, 9f, Mathf.Min(1f, G(x, z, RoostXZ.x, RoostXZ.y, 42f) * 1.3f));   // 용의 무덤 고원
            return Mathf.Lerp(-6f, land, edge);
        }

        // 유닛이 설 바닥 높이. 부유 성채 위에서는 성채 바닥, 그 밖에서는 지형.
        public static float GroundY(Vector3 p)
        {
            if (OnSky(p)) return SkyTop.y;
            return Height(p.x, p.z);
        }

        public static bool OnSky(Vector3 p)
        {
            float dx = p.x - SkyXZ.x, dz = p.z - SkyXZ.y;
            return dx * dx + dz * dz < SkyRadius * SkyRadius && p.y > SkyHeight - 8f;
        }

        public static Vector3 At(Vector2 xz, float dx = 0f, float dz = 0f)
        {
            float x = xz.x + dx, z = xz.y + dz;
            return new Vector3(x, Height(x, z), z);
        }

        public static void Build()
        {
            SpawnPoint = new Vector3(StartXZ.x, Height(StartXZ.x, StartXZ.y) + 1.2f, StartXZ.y);
            BuildTerrain();
            BuildWater();
            BuildGraveyard();
            BuildCrypt();
            BuildRuins();
            BuildRoost();
            BuildSkyKeep();
            BuildTrees();
            BuildRocks();
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
            Color grass = new Color(0.2f, 0.26f, 0.2f);
            Color grave = new Color(0.17f, 0.17f, 0.2f);
            Color ruins = new Color(0.33f, 0.31f, 0.29f);
            Color bone = new Color(0.5f, 0.46f, 0.4f);
            Color sand = new Color(0.34f, 0.32f, 0.34f);
            Color snow = new Color(0.62f, 0.62f, 0.7f);
            for (int y = 0; y < T; y++)
            {
                for (int x = 0; x < T; x++)
                {
                    float wx = -half + (x + 0.5f) / T * Size, wz = -half + (y + 0.5f) / T * Size;
                    float h = Height(wx, wz);
                    float hx = Height(wx + 1.5f, wz) - h, hz = Height(wx, wz + 1.5f) - h;
                    float slope = Mathf.Sqrt(hx * hx + hz * hz) / 1.5f;
                    Color c = Color.Lerp(grass, grave, G(wx, wz, StartXZ.x, StartXZ.y, 60f) + G(wx, wz, CryptXZ.x, CryptXZ.y, 40f));
                    c = Color.Lerp(c, ruins, G(wx, wz, RuinsXZ.x, RuinsXZ.y, 60f));
                    c = Color.Lerp(c, bone, G(wx, wz, RoostXZ.x, RoostXZ.y, 50f));
                    float v = Mathf.PerlinNoise(wx * 0.15f, wz * 0.15f) * 0.08f - 0.04f;
                    c = new Color(c.r + v, c.g + v, c.b + v);
                    if (h < 1.2f) c = Color.Lerp(sand, c, Mathf.InverseLerp(0.2f, 1.2f, h));
                    c = Color.Lerp(c, Rock, Mathf.InverseLerp(0.55f, 0.9f, slope));
                    if (h > 28f) c = Color.Lerp(c, snow, Mathf.InverseLerp(28f, 36f, h));
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
            w.layer = 2;
            w.transform.position = new Vector3(0f, 0.05f, 0f);
            w.transform.localScale = new Vector3(160f, 1f, 160f);
            var m = Util.NewMat(new Color(0.07f, 0.09f, 0.16f));
            if (m.HasProperty("_Smoothness")) m.SetFloat("_Smoothness", 0.9f);
            if (m.HasProperty("_Glossiness")) m.SetFloat("_Glossiness", 0.9f);
            w.GetComponent<Renderer>().sharedMaterial = m;
        }

        // 밟을 수 있는 도형 (원기둥·구는 MeshCollider로 바꿔야 늘린 모양대로 충돌함)
        static GameObject Solid(PrimitiveType t, Vector3 pos, Vector3 scale, Color c, Vector3 euler = default(Vector3))
        {
            var g = GameObject.CreatePrimitive(t);
            g.transform.position = pos;
            g.transform.localEulerAngles = euler;
            g.transform.localScale = scale;
            if (t != PrimitiveType.Cube)
            {
                Object.DestroyImmediate(g.GetComponent<Collider>());
                g.AddComponent<MeshCollider>().sharedMesh = g.GetComponent<MeshFilter>().sharedMesh;
            }
            g.GetComponent<Renderer>().sharedMaterial = Util.Mat(c);
            return g;
        }

        static void AddLight(Vector3 pos, Color c, float range, float intensity)
        {
            var lg = new GameObject("Light");
            lg.transform.position = pos;
            var l = lg.AddComponent<Light>();
            l.type = LightType.Point;
            l.color = c;
            l.range = range;
            l.intensity = intensity;
        }

        static void Grave(Vector3 p, float yaw, int kind)
        {
            Color stone = new Color(0.42f, 0.42f, 0.47f);
            var root = new GameObject("Grave").transform;
            root.position = p;
            root.rotation = Quaternion.Euler(0f, yaw, kind == 2 ? 6f : 0f);
            if (kind == 0)
            {
                Util.Part(PrimitiveType.Cube, root, new Vector3(0f, 0.45f, 0f), new Vector3(0.6f, 0.9f, 0.14f), stone);
                Util.Part(PrimitiveType.Cylinder, root, new Vector3(0f, 0.9f, 0f), new Vector3(0.6f, 0.07f, 0.6f), stone, new Vector3(90f, 0f, 0f));
            }
            else
            {
                Util.Part(PrimitiveType.Cube, root, new Vector3(0f, 0.6f, 0f), new Vector3(0.14f, 1.2f, 0.14f), stone);
                Util.Part(PrimitiveType.Cube, root, new Vector3(0f, 0.85f, 0f), new Vector3(0.6f, 0.14f, 0.14f), stone);
            }
            Util.Part(PrimitiveType.Cube, root, new Vector3(0f, 0.04f, 0.7f), new Vector3(0.8f, 0.1f, 1.5f), new Color(0.14f, 0.13f, 0.15f));
        }

        static void BuildGraveyard()
        {
            var rnd = new System.Random(21);
            for (int i = 0; i < 70; i++)
            {
                float a = (float)rnd.NextDouble() * Mathf.PI * 2f, d = 9f + (float)rnd.NextDouble() * 45f;
                float x = StartXZ.x + Mathf.Cos(a) * d, z = StartXZ.y + Mathf.Sin(a) * d;
                float h = Height(x, z);
                if (h < 1.5f) continue;
                Grave(new Vector3(x, h, z), rnd.Next(4) * 90f + rnd.Next(-12, 12), rnd.Next(3));
            }
            // 봉인의 제단 (시작·부활 지점)
            Vector3 p = At(StartXZ, 0f, 7f);
            Color stone = new Color(0.3f, 0.28f, 0.36f), soul = new Color(0.72f, 0.45f, 1f);
            Solid(PrimitiveType.Cylinder, p + Vector3.up * 0.15f, new Vector3(5f, 0.15f, 5f), stone);
            for (int i = 0; i < 4; i++)
            {
                float a = i * Mathf.PI * 0.5f + 0.4f;
                Vector3 q = p + new Vector3(Mathf.Cos(a) * 2f, 0f, Mathf.Sin(a) * 2f);
                Solid(PrimitiveType.Cube, q + Vector3.up * 1.4f, new Vector3(0.45f, 2.8f, 0.45f), stone, new Vector3(0f, a * Mathf.Rad2Deg, i == 2 ? 9f : 0f));
            }
            Util.Part(PrimitiveType.Sphere, null, p + Vector3.up * 1.6f, Vector3.one * 0.6f, soul, default(Vector3), true);
            AddLight(p + Vector3.up * 2f, soul, 14f, 3f);
        }

        static void BuildCrypt()
        {
            Vector3 p = At(CryptXZ, 0f, 9f);
            Color stone = new Color(0.27f, 0.27f, 0.32f), dark = new Color(0.1f, 0.1f, 0.13f);
            Solid(PrimitiveType.Cube, p + Vector3.up * 2.2f, new Vector3(9f, 4.4f, 6f), stone);
            Solid(PrimitiveType.Cube, p + new Vector3(0f, 4.9f, 0f), new Vector3(10f, 0.6f, 7f), dark);
            Util.Part(PrimitiveType.Cube, null, p + new Vector3(0f, 1.5f, -3.02f), new Vector3(2.2f, 3f, 0.1f), dark);
            for (int i = -1; i <= 1; i += 2)
            {
                Solid(PrimitiveType.Cylinder, p + new Vector3(i * 2.4f, 2.2f, -3.6f), new Vector3(0.6f, 2.2f, 0.6f), stone);
                Util.Part(PrimitiveType.Sphere, null, p + new Vector3(i * 2.4f, 4.7f, -3.6f), Vector3.one * 0.5f, new Color(0.5f, 1f, 0.55f), default(Vector3), true);
            }
            AddLight(p + new Vector3(0f, 3f, -5f), new Color(0.5f, 1f, 0.55f), 16f, 3f);
            var rnd = new System.Random(4);
            for (int i = 0; i < 16; i++)
            {
                float a = (float)rnd.NextDouble() * Mathf.PI * 2f, d = 8f + (float)rnd.NextDouble() * 14f;
                float x = CryptXZ.x + Mathf.Cos(a) * d, z = CryptXZ.y - 4f + Mathf.Sin(a) * d;
                if (z > p.z - 4f) continue;
                Grave(new Vector3(x, Height(x, z), z), rnd.Next(4) * 90f, rnd.Next(3));
            }
        }

        static void BuildRuins()
        {
            var rnd = new System.Random(8);
            Color stone = new Color(0.45f, 0.43f, 0.4f);
            for (int i = 0; i < 26; i++)
            {
                float a = (float)rnd.NextDouble() * Mathf.PI * 2f, d = 6f + (float)rnd.NextDouble() * 34f;
                float x = RuinsXZ.x + Mathf.Cos(a) * d, z = RuinsXZ.y + Mathf.Sin(a) * d;
                float h = Height(x, z);
                if (h < 1.5f) continue;
                int kind = rnd.Next(3);
                if (kind == 0)
                {
                    float ht = 2f + (float)rnd.NextDouble() * 5f;
                    Solid(PrimitiveType.Cylinder, new Vector3(x, h + ht * 0.5f, z), new Vector3(1.1f, ht * 0.5f, 1.1f), stone);
                }
                else if (kind == 1)
                {
                    Solid(PrimitiveType.Cube, new Vector3(x, h + 1.2f, z), new Vector3(5f + (float)rnd.NextDouble() * 4f, 2.6f, 0.8f), stone,
                          new Vector3(0f, rnd.Next(4) * 45f, 0f));
                }
                else
                {
                    Solid(PrimitiveType.Cylinder, new Vector3(x, h + 0.5f, z), new Vector3(1.1f, 2.2f, 1.1f), stone,
                          new Vector3(90f, rnd.Next(360), 0f));
                }
            }
        }

        static void BuildRoost()
        {
            // 거대한 갈비뼈와 두개골이 흩어진 용의 무덤
            Color bone = new Color(0.8f, 0.77f, 0.68f);
            Vector3 c = At(RoostXZ);
            for (int i = 0; i < 9; i++)
            {
                float z = -16f + i * 4f;
                for (int side = -1; side <= 1; side += 2)
                {
                    Vector3 p = c + new Vector3(side * 13f, 0f, z + 22f);
                    p.y = Height(p.x, p.z);
                    Solid(PrimitiveType.Cylinder, p + new Vector3(-side * 2f, 4f, 0f), new Vector3(0.7f, 4.6f, 0.7f), bone, new Vector3(0f, 0f, side * 24f));
                }
            }
            var rnd = new System.Random(15);
            for (int i = 0; i < 20; i++)
            {
                float a = (float)rnd.NextDouble() * Mathf.PI * 2f, d = 10f + (float)rnd.NextDouble() * 30f;
                float x = RoostXZ.x + Mathf.Cos(a) * d, z = RoostXZ.y + Mathf.Sin(a) * d;
                Util.Part(PrimitiveType.Capsule, null, new Vector3(x, Height(x, z) + 0.15f, z), new Vector3(0.3f, 1.2f, 0.3f), bone,
                          new Vector3(90f, rnd.Next(360), 0f));
            }
            AddLight(c + Vector3.up * 5f, new Color(1f, 0.45f, 0.2f), 34f, 2.5f);
        }

        static void BuildSkyKeep()
        {
            float x = SkyXZ.x, z = SkyXZ.y, top = SkyHeight;
            Color earth = new Color(0.2f, 0.17f, 0.26f), stone = new Color(0.25f, 0.22f, 0.34f), voidC = new Color(0.54f, 0.36f, 0.88f);
            Solid(PrimitiveType.Sphere, new Vector3(x, top - 7f, z), new Vector3(46f, 14f, 46f), earth);
            Solid(PrimitiveType.Cylinder, new Vector3(x, top, z), new Vector3(42f, 0.6f, 42f), stone);
            float y = top + 0.6f;
            SkyTop = new Vector3(x, y, z);
            for (int i = 0; i < 7; i++)
            {
                float a = i * 0.9f;
                Util.Part(PrimitiveType.Cube, null, new Vector3(x + Mathf.Cos(a) * 9f, top - 15f - (i % 3) * 3f, z + Mathf.Sin(a) * 9f),
                          new Vector3(4f, 7f, 4f), Rock, new Vector3(i * 13f, i * 29f, i * 7f));
            }
            // 부서진 성벽과 탑
            for (int i = 0; i < 10; i++)
            {
                if (i == 2 || i == 3 || i == 7) continue;     // 무너진 구간
                float a = i * Mathf.PI * 2f / 10f;
                Solid(PrimitiveType.Cube, new Vector3(x + Mathf.Cos(a) * 18.5f, y + 1.8f, z + Mathf.Sin(a) * 18.5f), new Vector3(1.2f, 3.6f, 11f), stone,
                      new Vector3(0f, -a * Mathf.Rad2Deg, 0f));
            }
            Solid(PrimitiveType.Cylinder, new Vector3(x - 9f, y + 5f, z + 8f), new Vector3(5f, 5f, 5f), stone);
            Util.Part(PrimitiveType.Sphere, null, new Vector3(x - 9f, y + 11.5f, z + 8f), Vector3.one * 2.2f, voidC, default(Vector3), true);
            AddLight(new Vector3(x - 9f, y + 11f, z + 8f), voidC, 40f, 4f);
            // 왕관 조각
            Util.Part(PrimitiveType.Cylinder, null, new Vector3(x, y + 0.5f, z), new Vector3(2f, 0.5f, 2f), stone);
            Util.Part(PrimitiveType.Cube, null, new Vector3(x, y + 1.7f, z), new Vector3(0.5f, 0.7f, 0.2f), new Color(1f, 0.8f, 0.3f), new Vector3(0f, 30f, 20f), true);
            AddLight(new Vector3(x, y + 2.5f, z), new Color(1f, 0.8f, 0.3f), 12f, 3f);
        }

        static void BuildTrees()
        {
            var rnd = new System.Random(7);
            int placed = 0;
            for (int i = 0; i < 4000 && placed < 230; i++)
            {
                float x = (float)(rnd.NextDouble() * 2 - 1) * 220f;
                float z = (float)(rnd.NextDouble() * 2 - 1) * 220f;
                float h = Height(x, z);
                if (h < 1.5f || h > 24f) continue;
                if (G(x, z, StartXZ.x, StartXZ.y, 22f) > 0.4f) continue;
                if (G(x, z, RoostXZ.x, RoostXZ.y, 34f) > 0.4f) continue;
                if (G(x, z, CryptXZ.x, CryptXZ.y, 14f) > 0.4f) continue;
                if (Mathf.Abs(Height(x + 2f, z) - h) > 2.5f) continue;
                float forest = G(x, z, -130f, 0f, 95f);
                if (rnd.NextDouble() > 0.07 + forest * 0.9) continue;
                DeadTree(new Vector3(x, h, z), 0.8f + (float)rnd.NextDouble() * 0.8f, rnd);
                placed++;
            }
        }

        static void DeadTree(Vector3 p, float s, System.Random rnd)
        {
            Color bark = new Color(0.17f, 0.14f, 0.15f);
            var root = new GameObject("DeadTree");
            root.layer = 2;
            root.transform.position = p;
            root.transform.rotation = Quaternion.Euler(0f, rnd.Next(360), 0f);
            Transform tr = root.transform;
            Util.Part(PrimitiveType.Cylinder, tr, new Vector3(0f, 2f * s, 0f), new Vector3(0.45f * s, 2f * s, 0.45f * s), bark);
            for (int i = 0; i < 4; i++)
            {
                float a = i * 90f + rnd.Next(-25, 25);
                float y = (2.2f + i * 0.55f) * s;
                var b = Util.Pivot(tr, new Vector3(0f, y, 0f));
                b.localRotation = Quaternion.Euler(0f, a, 0f);
                Util.Part(PrimitiveType.Cylinder, b, new Vector3(0f, 0.6f * s, 0.75f * s), new Vector3(0.14f * s, 1f * s, 0.14f * s), bark, new Vector3(50f, 0f, 0f));
                Util.Part(PrimitiveType.Cylinder, b, new Vector3(0f, 1.45f * s, 1.5f * s), new Vector3(0.07f * s, 0.55f * s, 0.07f * s), bark, new Vector3(25f, 0f, 0f));
            }
            var col = root.AddComponent<CapsuleCollider>();
            col.center = new Vector3(0f, 1.5f * s, 0f);
            col.radius = 0.3f * s;
            col.height = 3f * s;
        }

        static void BuildRocks()
        {
            var rnd = new System.Random(11);
            int placed = 0;
            for (int i = 0; i < 800 && placed < 60; i++)
            {
                float x = (float)(rnd.NextDouble() * 2 - 1) * 210f;
                float z = (float)(rnd.NextDouble() * 2 - 1) * 210f;
                float h = Height(x, z);
                if (h < 1f || G(x, z, StartXZ.x, StartXZ.y, 25f) > 0.4f) continue;
                if (rnd.NextDouble() > 0.2) continue;
                float s = 0.8f + (float)rnd.NextDouble() * 1.8f;
                Solid(PrimitiveType.Sphere, new Vector3(x, h + s * 0.2f, z), new Vector3(s * 1.4f, s, s * 1.2f), Rock,
                      new Vector3(0f, (float)rnd.NextDouble() * 360f, 0f));
                placed++;
            }
        }
    }
}
