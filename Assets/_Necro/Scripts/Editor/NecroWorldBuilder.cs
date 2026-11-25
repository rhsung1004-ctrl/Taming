using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using Debug = UnityEngine.Debug;

namespace Necro.EditorTools
{
    // Tools → Necro → 월드 → 1. 1장 오픈월드 만들기
    // 월드 생성기(Tools/WorldGen)가 만든 데이터(Assets/_Necro/Art/World/Ch1/Data~)를 파일로 직접 읽어
    // Assets/_Necro/Scenes/World_Ch1.unity 를 만든다. 데이터 규격은 Tools/WorldGen/SPEC.md 를 그대로 따른다.
    public static class NecroWorldBuilder
    {
        public const string WorldFolder = "Assets/_Necro/Art/World/Ch1";
        public const string DataFolder = WorldFolder + "/Data~";
        public const string TerrainTexFolder = WorldFolder + "/Terrain";
        public const string MapPath = WorldFolder + "/map.png";
        public const string GeneratedFolder = WorldFolder + "/Generated";
        public const string WorldMatFolder = "Assets/_Necro/Art/Materials/World";
        public const string SceneFolder = "Assets/_Necro/Scenes";
        public const string ScenePath = SceneFolder + "/World_Ch1.unity";
        const string TerrainShader = "Universal Render Pipeline/Terrain/Lit";
        const string WaterShader = "Necro/Water";
        const string ParticleShader = "Necro/SoulParticle";
        const int CellSize = 256;                       // 소품을 묶는 칸 (m)
        const float DefaultFogDensity = 0.0055f;        // world.json 에 fog 가 없을 때 (오픈월드용으로 옅게)

        // 카메라 먼 거리 = 월드 한 변 × 이 값 (대각선 √2 ≈ 1.414 보다 조금 길게). 아래 ApplyWorldAtmosphere 설명 참고
        const float WorldFarClipMargin = 1.42f;
        const float WorldFarClipMin = 2000f;

        // 지형 풀 (나중에 [Header]·Tooltip 이 붙은 튜닝 값 ScriptableObject 로 옮긴다).
        // 지형 풀은 LOD 가 없어 먼 풀도 LOD0 메쉬(지금 한 포기 410~650 삼각형)를 그대로 그린다.
        // 실제 데이터로 세어 보면 110m 일 때 시작 위치 화면 안 풀만 약 3,900만 삼각형, 70m 면 약 2,000만 (밀도 1 기준).
        // 70m 에서 Exp2 안개(0.0048)는 약 11% 라 풀이 끝나는 곳이 조금 보일 수 있다 (110m 에서도 약 24% 였다).
        const float DetailDistance = NecroProps.TerrainDetailDistance;   // 지형 풀 전용 재질의 거리 축소도 이 값을 쓴다
        // 풀 밀도 배율. 풀 프로토타입이 useDensityScaling = true 라 모든 풀이 고르게 줄어든다
        // (품질 설정의 terrainDetailDensityScale 이 한 번 더 곱해진다). 1 = 생성기 밀도 그대로
        const float DetailDensity = 0.75f;
        static readonly string[] FxTypes = { "mist", "wisps", "soulfire", "fireflies" };
        static readonly string Title = "1장 오픈월드 만들기";

        // ───────────── 읽은 데이터 ─────────────
        class LayerDesc { public string name, albedo, normal; public float tile = 6f, smoothness = 0.05f; }
        class DetailDesc { public string asset; public float maxPerCell = 3f, minScale = 0.8f, maxScale = 1.3f; }
        class ObjDesc { public string a; public Vector3 p; public Quaternion q = Quaternion.identity; public float s = 1f; }
        class LightDesc { public Vector3 p; public Color c; public float i, r, far; public bool flicker; }   // far: 끄는 거리 덮어쓰기 (0 = 없음)
        class WaterDesc { public Vector3 p; public Vector2 size; public float yaw; }
        class FxDesc { public string type; public Vector3 p; public float r; }

        class WorldData
        {
            public float size, height, seaLevel;
            public int heightRes, tiles, splatRes, detailRes;
            public Vector3 spawn;
            public float spawnYaw;
            public List<LayerDesc> layers = new List<LayerDesc>();
            public List<DetailDesc> details = new List<DetailDesc>();
            public List<NecroPoi> pois = new List<NecroPoi>();
            public bool hasFog;
            public Color fogColor;
            public float fogDensity;
            public Vector2 mapMin, mapSize;                       // 지도 그림이 덮는 범위 (world.json map, 없으면 지형 전체)
            public ushort[] heights;                              // heightRes × heightRes, 행 = Z(남→북), 열 = X(서→동)
            public Color32[] splat0, splat1, detail0, detail1;   // GetPixels32: 행 0 = 아래 줄 = 남쪽
            public List<string> treeProtos = new List<string>();
            public List<float[]> trees = new List<float[]>();     // [proto, x, z, yawDeg, scale]
            public List<ObjDesc> objects = new List<ObjDesc>();
            public List<LightDesc> lights = new List<LightDesc>();
            public List<WaterDesc> water = new List<WaterDesc>();
            public List<FxDesc> fx = new List<FxDesc>();

            public int TileRes { get { return (heightRes - 1) / tiles + 1; } }
            public float TileSize { get { return size / tiles; } }

            // 지형 높이 (m), 높이 격자 쌍선형 보간
            public float HeightAt(float x, float z) { return NecroWorldGrid.HeightAt(heights, heightRes, size, height, x, z); }
        }

        class Stats
        {
            public int tiles, layers, detailProtos, treeProtos, trees, props, propLights, lights, water, fx, pois;
            public long details;
            public int skippedTrees, skippedObjects;
        }

        // ───────────── 메뉴 ─────────────
        [MenuItem("Tools/Necro/월드/1. 1장 오픈월드 만들기", priority = 101)]
        public static void BuildMenu()
        {
            if (NecroEditorUtil.FindShader(TerrainShader, true) == null) return;
            if (NecroEditorUtil.FindShader(NecroProps.FoliageShader, true) == null) return;
            if (NecroEditorUtil.FindShader(WaterShader, true) == null) return;
            if (NecroEditorUtil.FindShader(ParticleShader, true) == null) return;

            var sw = Stopwatch.StartNew();
            var errors = new List<string>();
            var warnings = new List<string>();
            WorldData w;
            try
            {
                EditorUtility.DisplayProgressBar(Title, "데이터 읽는 중", 0f);
                w = ReadData(errors, warnings);
            }
            finally { EditorUtility.ClearProgressBar(); }
            if (w == null || errors.Count > 0)
            {
                Debug.LogError("[Necro] 1장 오픈월드 데이터를 읽지 못했어요 (" + DataFolder + ")\n" + string.Join("\n", errors.ToArray()));
                EditorUtility.DisplayDialog(Title, "월드 데이터에 문제가 있어 멈췄어요.\n폴더: " + DataFolder + "\n\n" + NecroEditorUtil.Join(errors, 14), "확인");
                return;
            }

            // 소품 프리팹 확인 (없으면 0번 도구를 먼저 돌릴지 묻는다)
            var missing = MissingPrefabs(w);
            if (missing.Count > 0)
            {
                int choice = EditorUtility.DisplayDialogComplex(Title,
                    "소품 프리팹이 " + missing.Count + "종 없어요 (" + NecroProps.PrefabFolder + ").\n\n" + NecroEditorUtil.Join(missing, 8) +
                    "\n'0. 소품 가져오기 설정 + 프리팹 만들기'를 먼저 실행할까요?",
                    "0번 실행 후 계속", "취소", "빠진 것 빼고 계속");
                if (choice == 1) return;
                if (choice == 0)
                {
                    NecroProps.BuildAll(warnings);
                    missing = MissingPrefabs(w);
                }
                if (missing.Count > 0) warnings.Add("프리팹이 없어 빼고 만든 소품: " + string.Join(", ", missing.ToArray()));
            }

            if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
            if (File.Exists(NecroEditorUtil.FullPath(ScenePath)))
            {
                int choice = EditorUtility.DisplayDialogComplex(Title,
                    "이미 만든 1장 월드 장면이 있어요. 새로 만들면 그 장면에서 직접 배치·수정한 것이 사라집니다.\n" +
                    "(지형 데이터·재질은 같은 파일을 고쳐 쓰므로 그대로 이어집니다)",
                    "기존 장면 열기", "취소", "새로 만들기");
                if (choice == 1) return;
                if (choice == 0) { EditorSceneManager.OpenScene(ScenePath); return; }
            }

            var st = new Stats();
            try
            {
                Build(w, warnings, st);
            }
            catch (System.Exception e)
            {
                EditorUtility.ClearProgressBar();
                Debug.LogException(e);
                EditorUtility.DisplayDialog(Title, "만드는 중에 오류가 났어요:\n" + e.Message + "\n\nConsole 의 빨간 메시지를 Claude 에게 보내 주세요.", "확인");
                return;
            }
            finally { EditorUtility.ClearProgressBar(); }

            string summary = "[Necro] 1장 오픈월드를 만들었어요: " + ScenePath +
                "\n지형 " + st.tiles + "타일 (" + w.size + "m × " + w.size + "m, 높이 " + w.height + "m), 지형 층 " + st.layers + "개" +
                "\n풀 " + st.detailProtos + "종 · " + st.details.ToString("N0") + "포기, 지형 나무 " + st.treeProtos + "종 · " + st.trees.ToString("N0") + "그루" +
                (st.skippedTrees > 0 ? " (뺀 것 " + st.skippedTrees + ")" : "") +
                "\n소품 " + st.props.ToString("N0") + "개 (그중 광원 달린 것 " + st.propLights + ")" + (st.skippedObjects > 0 ? " (뺀 것 " + st.skippedObjects + ")" : "") +
                ", 따로 놓은 광원 " + st.lights + ", 물 " + st.water + ", 효과 " + st.fx + ", 이름 있는 장소 " + st.pois +
                "\n걸린 시간 " + sw.Elapsed.TotalSeconds.ToString("0.0") + "초" + (warnings.Count > 0 ? ", 경고 " + warnings.Count + "개 (아래)" : "") +
                "\nPlay 를 누르고 걸어 다니며 확인하세요. M = 지도, F3 = 분위기 바꾸기.";
            Debug.Log(summary);
            if (warnings.Count > 0) Debug.LogWarning("[Necro] 1장 오픈월드 경고\n" + string.Join("\n", warnings.ToArray()));
        }

        static List<string> MissingPrefabs(WorldData w)
        {
            var names = new HashSet<string>();
            foreach (var d in w.details) names.Add(d.asset);
            foreach (var t in w.treeProtos) names.Add(t);
            foreach (var o in w.objects) names.Add(o.a);
            var missing = new List<string>();
            foreach (var n in names) if (NecroProps.LoadPrefab(n) == null) missing.Add(n);
            missing.Sort(System.StringComparer.Ordinal);
            return missing;
        }

        // ───────────── 데이터 읽기 ─────────────
        static string DataPath(string file) { return NecroEditorUtil.FullPath(DataFolder + "/" + file); }

        static object ReadJson(string file, List<string> errors)
        {
            string path = DataPath(file);
            if (!File.Exists(path)) { errors.Add(file + " 파일이 없습니다"); return null; }
            try { return NecroJson.Parse(File.ReadAllText(path)); }
            catch (System.Exception e) { errors.Add(file + " 형식이 틀렸습니다: " + e.Message); return null; }
        }

        static bool IsPow2(int v) { return v > 0 && (v & (v - 1)) == 0; }

        static WorldData ReadData(List<string> errors, List<string> warnings)
        {
            if (!Directory.Exists(NecroEditorUtil.FullPath(DataFolder)))
            {
                errors.Add("데이터 폴더가 없습니다: " + DataFolder + " (월드 생성기 결과를 받았는지, git lfs pull 을 했는지 확인)");
                return null;
            }
            var w = new WorldData();

            // world.json
            var ctx = new JsonReadContext("world.json");
            var root = ctx.Obj(ReadJson("world.json", errors), "전체");
            if (root == null) { errors.AddRange(ctx.errors); return null; }
            double version = ctx.Num(root, "version", "전체", 1, false);
            if ((int)version != 1) warnings.Add("world.json version 이 " + version + " 입니다 (도구는 1 기준)");
            w.size = (float)ctx.Num(root, "size", "전체", 2048, true);
            w.height = (float)ctx.Num(root, "height", "전체", 320, true);
            w.heightRes = (int)ctx.Num(root, "heightRes", "전체", 2049, true);
            w.tiles = (int)ctx.Num(root, "tiles", "전체", 2, true);
            w.splatRes = (int)ctx.Num(root, "splatRes", "전체", 2048, true);
            w.detailRes = (int)ctx.Num(root, "detailRes", "전체", 2048, true);
            w.seaLevel = (float)ctx.Num(root, "seaLevel", "전체", 0, false);
            if (w.tiles < 1 || w.tiles > 8) ctx.Fail("tiles", "1~8 이어야 합니다 (지금 " + w.tiles + ")");
            else
            {
                if ((w.heightRes - 1) % w.tiles != 0 || !IsPow2((w.heightRes - 1) / w.tiles) || (w.heightRes - 1) / w.tiles < 32 || (w.heightRes - 1) / w.tiles > 4096)
                    ctx.Fail("heightRes", "(heightRes − 1) / tiles 가 32~4096 사이의 2의 거듭제곱이어야 합니다 (지금 " + w.heightRes + ")");
                if (w.splatRes % w.tiles != 0 || !IsPow2(w.splatRes / w.tiles) || w.splatRes / w.tiles < 16 || w.splatRes / w.tiles > 4096)
                    ctx.Fail("splatRes", "splatRes / tiles 가 16~4096 사이의 2의 거듭제곱이어야 합니다 (지금 " + w.splatRes + ")");
                if (w.detailRes % w.tiles != 0 || (w.detailRes / w.tiles) % 32 != 0 || w.detailRes / w.tiles > 4048)
                    ctx.Fail("detailRes", "detailRes / tiles 가 32의 배수이고 4048 이하여야 합니다 (지금 " + w.detailRes + ")");
            }
            if (w.size <= 0f || w.height <= 0f) ctx.Fail("size/height", "0보다 커야 합니다");

            var spawn = root.ContainsKey("spawn") ? ctx.Obj(root["spawn"], "spawn") : null;
            if (spawn == null) ctx.Fail("spawn", "주인공 시작 위치가 없습니다");
            else
            {
                w.spawn = ctx.Vec3(spawn, "p", "spawn", Vector3.zero, true);
                w.spawnYaw = (float)ctx.Num(spawn, "yaw", "spawn", 0, false);
            }

            var layers = ctx.Arr(root, "layers", "전체", true);
            if (layers != null)
            {
                if (layers.Count == 0 || layers.Count > 8) ctx.Fail("layers", "지형 층은 1~8개여야 합니다 (지금 " + layers.Count + ")");
                for (int i = 0; i < layers.Count && i < 8; i++)
                {
                    string where = "layers[" + i + "]";
                    var d = ctx.Obj(layers[i], where);
                    if (d == null) continue;
                    var l = new LayerDesc
                    {
                        name = ctx.Str(d, "name", where, "layer" + i, true),
                        albedo = ctx.Str(d, "albedo", where, null, true),
                        normal = ctx.Str(d, "normal", where, null, false),
                        tile = (float)ctx.Num(d, "tile", where, 6, false),
                        smoothness = (float)ctx.Num(d, "smoothness", where, 0.05, false)
                    };
                    if (l.albedo != null && !File.Exists(NecroEditorUtil.FullPath(TerrainTexFolder + "/" + l.albedo)))
                        ctx.Fail(where, "층 텍스처가 없습니다: " + TerrainTexFolder + "/" + l.albedo);
                    if (l.normal != null && !File.Exists(NecroEditorUtil.FullPath(TerrainTexFolder + "/" + l.normal)))
                    {
                        warnings.Add("지형 층 " + l.name + ": 노멀 텍스처가 없어 빼고 만들었어요 (" + l.normal + ")");
                        l.normal = null;
                    }
                    w.layers.Add(l);
                }
            }

            var details = ctx.Arr(root, "details", "전체", false);
            if (details != null)
            {
                if (details.Count > 8) ctx.Fail("details", "풀 종류는 8개까지입니다 (지금 " + details.Count + ")");
                for (int i = 0; i < details.Count && i < 8; i++)
                {
                    string where = "details[" + i + "]";
                    var d = ctx.Obj(details[i], where);
                    if (d == null) continue;
                    w.details.Add(new DetailDesc
                    {
                        asset = ctx.Str(d, "asset", where, "", true),
                        maxPerCell = (float)ctx.Num(d, "maxPerCell", where, 3, true),
                        minScale = (float)ctx.Num(d, "minScale", where, 0.8, false),
                        maxScale = (float)ctx.Num(d, "maxScale", where, 1.3, false)
                    });
                }
            }

            var pois = ctx.Arr(root, "pois", "전체", false);
            if (pois != null)
                for (int i = 0; i < pois.Count; i++)
                {
                    string where = "pois[" + i + "]";
                    var d = ctx.Obj(pois[i], where);
                    if (d == null) continue;
                    w.pois.Add(new NecroPoi
                    {
                        id = ctx.Str(d, "id", where, "poi" + i, false),
                        name = ctx.Str(d, "name", where, "이름 없는 장소", true),
                        position = ctx.Vec3(d, "p", where, Vector3.zero, true),
                        radius = (float)ctx.Num(d, "r", where, 30, false),
                        showOnMap = ctx.Bool(d, "map", true)
                    });
                }

            // 지도 범위 (선택): 없으면 지형 전체. 걸어 다니는 범위만 크게 보이게 생성기가 bounds + 여유로 넣는다
            w.mapMin = Vector2.zero;
            w.mapSize = new Vector2(w.size, w.size);
            if (root.ContainsKey("map") && root["map"] != null)
            {
                var map = ctx.Obj(root["map"], "map");
                if (map != null)
                {
                    var mn = ctx.Floats(map, "min", 2, "map", true);
                    var mx = ctx.Floats(map, "max", 2, "map", true);
                    if (mn != null && mx != null)
                    {
                        if (mx[0] - mn[0] < 1f || mx[1] - mn[1] < 1f) ctx.Fail("map", "max 가 min 보다 커야 합니다");
                        else
                        {
                            w.mapMin = new Vector2(mn[0], mn[1]);
                            w.mapSize = new Vector2(mx[0] - mn[0], mx[1] - mn[1]);
                        }
                    }
                }
            }

            if (root.ContainsKey("fog") && root["fog"] != null)
            {
                var fog = ctx.Obj(root["fog"], "fog");
                if (fog != null)
                {
                    w.hasFog = true;
                    w.fogColor = ctx.Col(fog, "color", "fog", new Color(0.16f, 0.12f, 0.27f), true);
                    w.fogDensity = (float)ctx.Num(fog, "density", "fog", DefaultFogDensity, true);
                }
            }
            errors.AddRange(ctx.errors);
            if (errors.Count > 0) return w;

            // height.r16
            string hp = DataPath("height.r16");
            if (!File.Exists(hp)) errors.Add("height.r16 파일이 없습니다");
            else
            {
                var bytes = File.ReadAllBytes(hp);
                long expect = (long)w.heightRes * w.heightRes * 2;
                if (bytes.Length != expect)
                    errors.Add("height.r16 크기가 틀렸습니다: " + bytes.Length + " 바이트 (heightRes " + w.heightRes + " → " + expect + " 바이트여야 함)");
                else
                {
                    w.heights = new ushort[w.heightRes * w.heightRes];
                    for (int i = 0; i < w.heights.Length; i++) w.heights[i] = (ushort)(bytes[i * 2] | (bytes[i * 2 + 1] << 8));   // 리틀엔디언
                }
            }

            // splat / detail PNG
            w.splat0 = LoadPng("splat_0.png", w.splatRes, errors);
            if (w.layers.Count > 4) w.splat1 = LoadPng("splat_1.png", w.splatRes, errors);
            if (w.details.Count > 0) w.detail0 = LoadPng("detail_0.png", w.detailRes, errors);
            if (w.details.Count > 4) w.detail1 = LoadPng("detail_1.png", w.detailRes, errors);

            ReadTrees(w, errors);
            ReadObjects(w, errors, warnings);
            return w;
        }

        static Color32[] LoadPng(string file, int res, List<string> errors)
        {
            string path = DataPath(file);
            if (!File.Exists(path)) { errors.Add(file + " 파일이 없습니다"); return null; }
            var tex = new Texture2D(2, 2, TextureFormat.RGBA32, false, true);
            try
            {
                if (!ImageConversion.LoadImage(tex, File.ReadAllBytes(path), false)) { errors.Add(file + " 를 그림으로 읽지 못했습니다"); return null; }
                if (tex.width != res || tex.height != res)
                {
                    errors.Add(file + " 크기가 " + tex.width + " × " + tex.height + " 입니다 (" + res + " × " + res + " 여야 함)");
                    return null;
                }
                return tex.GetPixels32();      // 아래 줄부터: 행 0 = 남쪽 (PNG 맨 윗줄 = 북쪽 규칙과 맞다)
            }
            finally { Object.DestroyImmediate(tex); }
        }

        static void ReadTrees(WorldData w, List<string> errors)
        {
            var ctx = new JsonReadContext("trees.json");
            var root = ctx.Obj(ReadJson("trees.json", errors), "전체");
            if (root == null) { errors.AddRange(ctx.errors); return; }
            var protos = ctx.Arr(root, "prototypes", "전체", true);
            if (protos != null)
                for (int i = 0; i < protos.Count; i++)
                {
                    var s = protos[i] as string;
                    if (s == null) ctx.Fail("prototypes[" + i + "]", "소품 이름(글자)이어야 합니다");
                    w.treeProtos.Add(s ?? "");
                }
            var inst = ctx.Arr(root, "instances", "전체", true);
            if (inst != null)
                for (int i = 0; i < inst.Count && ctx.errors.Count < 20; i++)
                {
                    var f = ctx.Floats(inst[i], 5, "instances[" + i + "]");
                    if (f == null) continue;
                    int proto = (int)f[0];
                    if (proto < 0 || proto >= w.treeProtos.Count || proto != f[0])
                    {
                        ctx.Fail("instances[" + i + "]", "프로토타입 번호 " + f[0] + " 가 prototypes 범위(0~" + (w.treeProtos.Count - 1) + ")를 벗어났습니다");
                        continue;
                    }
                    w.trees.Add(f);
                }
            errors.AddRange(ctx.errors);
        }

        static void ReadObjects(WorldData w, List<string> errors, List<string> warnings)
        {
            var ctx = new JsonReadContext("objects.json");
            var root = ctx.Obj(ReadJson("objects.json", errors), "전체");
            if (root == null) { errors.AddRange(ctx.errors); return; }

            var objs = ctx.Arr(root, "objects", "전체", true);
            if (objs != null)
                for (int i = 0; i < objs.Count && ctx.errors.Count < 20; i++)
                {
                    string where = "objects[" + i + "]";
                    var d = ctx.Obj(objs[i], where);
                    if (d == null) continue;
                    var o = new ObjDesc { a = ctx.Str(d, "a", where, "", true), p = ctx.Vec3(d, "p", where, Vector3.zero, true) };
                    var q = ctx.Floats(d, "q", 4, where, false);
                    if (q != null)
                    {
                        float len = Mathf.Sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3]);
                        if (len < 1e-6f) ctx.Fail(where, "쿼터니언 q 의 길이가 0 입니다");
                        else o.q = new Quaternion(q[0] / len, q[1] / len, q[2] / len, q[3] / len);   // (x, y, z, w) Unity 좌표
                    }
                    o.s = (float)ctx.Num(d, "s", where, 1, false);
                    w.objects.Add(o);
                }

            var lights = ctx.Arr(root, "lights", "전체", false);
            if (lights != null)
                for (int i = 0; i < lights.Count && ctx.errors.Count < 20; i++)
                {
                    string where = "lights[" + i + "]";
                    var d = ctx.Obj(lights[i], where);
                    if (d == null) continue;
                    w.lights.Add(new LightDesc
                    {
                        p = ctx.Vec3(d, "p", where, Vector3.zero, true),
                        c = ctx.Col(d, "c", where, new Color(0.62f, 0.35f, 1f), false),
                        i = (float)ctx.Num(d, "i", where, 6, false),
                        r = (float)ctx.Num(d, "r", where, 10, false),
                        far = Mathf.Max(0f, (float)ctx.Num(d, "far", where, 0, false)),
                        flicker = ctx.Bool(d, "flicker", true)
                    });
                }

            var water = ctx.Arr(root, "water", "전체", false);
            if (water != null)
                for (int i = 0; i < water.Count && ctx.errors.Count < 20; i++)
                {
                    string where = "water[" + i + "]";
                    var d = ctx.Obj(water[i], where);
                    if (d == null) continue;
                    var size = ctx.Floats(d, "size", 2, where, true);
                    w.water.Add(new WaterDesc
                    {
                        p = ctx.Vec3(d, "p", where, Vector3.zero, true),
                        size = size != null ? new Vector2(size[0], size[1]) : new Vector2(10f, 10f),
                        yaw = (float)ctx.Num(d, "yaw", where, 0, false)
                    });
                }

            var fx = ctx.Arr(root, "fx", "전체", false);
            if (fx != null)
                for (int i = 0; i < fx.Count && ctx.errors.Count < 20; i++)
                {
                    string where = "fx[" + i + "]";
                    var d = ctx.Obj(fx[i], where);
                    if (d == null) continue;
                    string type = ctx.Str(d, "type", where, "", true);
                    if (System.Array.IndexOf(FxTypes, type) < 0)
                    {
                        warnings.Add("objects.json " + where + ": 알 수 없는 효과 종류 '" + type + "' (mist, wisps, soulfire, fireflies 중 하나) → 뺐어요");
                        continue;
                    }
                    w.fx.Add(new FxDesc { type = type, p = ctx.Vec3(d, "p", where, Vector3.zero, true), r = (float)ctx.Num(d, "r", where, 20, false) });
                }
            errors.AddRange(ctx.errors);
        }

        // ───────────── 장면 만들기 ─────────────
        static void Progress(string msg, float t) { EditorUtility.DisplayProgressBar(Title, msg, Mathf.Clamp01(t)); }

        static void Build(WorldData w, List<string> warnings, Stats st)
        {
            NecroEditorUtil.EnsureFolder(SceneFolder);
            NecroEditorUtil.EnsureFolder(GeneratedFolder);
            NecroEditorUtil.EnsureFolder(WorldMatFolder);
            var manifest = NecroProps.LoadManifest(null);
            ConfigureWorldTextures();

            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            ApplyLightingSettings();

            // 카메라와 분위기
            Progress("분위기 (하늘·달빛·안개·후처리)", 0.02f);
            var camGo = new GameObject("Main Camera");
            camGo.tag = "MainCamera";
            var cam = camGo.AddComponent<Camera>();
            camGo.AddComponent<AudioListener>();
            var moon = NecroLookTools.ApplyLook();
            ApplyWorldAtmosphere(w, cam, moon);

            // 지형
            var terrains = BuildTerrain(w, manifest, warnings, st);

            // 소품·광원·물·효과
            BuildObjects(w, warnings, st);
            BuildLights(w, st);
            BuildWater(w, st);
            BuildFx(w, st);

            // 주인공 (임시 마네킹) — 시작 위치
            Progress("주인공과 월드 시스템", 0.95f);
            var hero = NecroLookTools.BuildPlaceholderHero();
            Vector3 sp = w.spawn;
            sp.y = Mathf.Max(sp.y, w.HeightAt(sp.x, sp.z)) + 0.05f;
            hero.transform.position = sp;
            hero.transform.rotation = Quaternion.Euler(0f, w.spawnYaw, 0f);
            Quaternion yaw = Quaternion.Euler(0f, w.spawnYaw, 0f);
            camGo.transform.position = sp + yaw * new Vector3(0f, 2.4f, -5.5f);
            camGo.transform.rotation = Quaternion.LookRotation(sp + Vector3.up * 1.4f - camGo.transform.position);
            var player = NecroSetupTools.BuildPlayer(hero);

            BuildSystems(w, player.transform, st);
            BuildAmbient(player.transform);

            if (terrains != null && terrains.Length > 0) Selection.activeGameObject = player;
            var view = SceneView.lastActiveSceneView;
            if (view != null) view.LookAt(sp + Vector3.up, Quaternion.Euler(28f, w.spawnYaw, 0f), 30f);

            Progress("장면 저장", 0.99f);
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, ScenePath);
            AssetDatabase.SaveAssets();
        }

        // 텍스처 가져오기 설정 (지형 층, 지도). 후처리기도 같은 설정을 쓰지만, 이미 가져온 파일은 여기서 다시 맞춘다
        static void ConfigureWorldTextures()
        {
            var paths = new List<string>();
            string tf = NecroEditorUtil.FullPath(TerrainTexFolder);
            if (Directory.Exists(tf))
                foreach (var f in Directory.GetFiles(tf))
                {
                    string ext = Path.GetExtension(f).ToLowerInvariant();
                    if (ext == ".png" || ext == ".jpg" || ext == ".jpeg") paths.Add(TerrainTexFolder + "/" + Path.GetFileName(f));
                }
            if (File.Exists(NecroEditorUtil.FullPath(MapPath))) paths.Add(MapPath);
            var reimport = new List<TextureImporter>();
            foreach (var p in paths)
            {
                var ti = AssetImporter.GetAtPath(p) as TextureImporter;
                if (ti != null && NecroProps.ConfigureTexture(ti, p)) reimport.Add(ti);
            }
            if (reimport.Count == 0) return;
            AssetDatabase.StartAssetEditing();
            try { foreach (var ti in reimport) ti.SaveAndReimport(); }
            finally { AssetDatabase.StopAssetEditing(); }
        }

        // 굽는 조명은 쓰지 않는다 (2km 지형을 실수로 굽기 시작하지 않게)
        static void ApplyLightingSettings()
        {
            string path = GeneratedFolder + "/WorldLighting.lighting";
            var ls = AssetDatabase.LoadAssetAtPath<LightingSettings>(path);
            if (ls == null)
            {
                ls = new LightingSettings { name = "WorldLighting" };
                AssetDatabase.CreateAsset(ls, path);
            }
            ls.bakedGI = false;
            ls.realtimeGI = false;
            EditorUtility.SetDirty(ls);
            Lightmapping.lightingSettings = ls;
        }

        // world.json 의 안개를 반영하고, 하늘·카메라·분위기 프리셋을 오픈월드에 맞춘다
        static void ApplyWorldAtmosphere(WorldData w, Camera cam, Light moon)
        {
            Color fogColor = w.hasFog ? w.fogColor : RenderSettings.fogColor;
            float density = w.hasFog ? Mathf.Max(0.0001f, w.fogDensity) : DefaultFogDensity;
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.ExponentialSquared;
            RenderSettings.fogColor = fogColor;
            RenderSettings.fogDensity = density;

            // 하늘: 룩 장면과 따로 쓰는 복사본 (지평선 = 안개 색)
            string skyPath = WorldMatFolder + "/NecroSky_World.mat";
            var sky = AssetDatabase.LoadAssetAtPath<Material>(skyPath);
            if (sky == null)
            {
                var src = RenderSettings.skybox;
                sky = src != null ? new Material(src) : new Material(Shader.Find("Necro/Sky"));
                sky.name = "NecroSky_World";
                AssetDatabase.CreateAsset(sky, skyPath);
            }
            sky.SetColor("_HorizonColor", fogColor);
            if (moon != null)
            {
                Vector3 toMoon = -moon.transform.forward;
                sky.SetVector("_MoonDir", new Vector4(toMoon.x, toMoon.y, toMoon.z, 0f));
            }
            EditorUtility.SetDirty(sky);
            RenderSettings.skybox = sky;

            // 월드 대각선까지 그린다. 안개가 다 덮은 바깥 산줄기도 안개색 윤곽으로 하늘보다 밝게 보여야 한다
            // (Necro/Sky 는 지평선 높이만 안개색이고 그보다 높은 하늘은 더 어둡다). 안개 거리에서 자르면
            // 그 방향 지평선이 평평해지고, 잘린 거리에 걸친 산은 단면이 보인다.
            // reversed-Z 라 near 0.2 / far 약 2,900 도 정밀도 문제가 없고, 먼 지형은 픽셀 오차 4 의 낮은 LOD,
            // 소품은 LODGroup 컬링(META.cull)이 있어 비용이 거의 늘지 않는다
            cam.farClipPlane = Mathf.Max(WorldFarClipMin, w.size * WorldFarClipMargin);
            cam.nearClipPlane = 0.2f;

            // 분위기 프리셋(F3): 안개 세기를 오픈월드 비율로 줄이고 기본 프리셋 안개 색을 world.json 에 맞춘다
            var volGo = GameObject.Find("Necro Look Volume");
            var cycler = volGo != null ? volGo.GetComponent<LookPresetCycler>() : null;
            if (cycler != null && cycler.presets != null && cycler.presets.Length > 0)
            {
                float baseDensity = cycler.presets[0].fogDensity > 0f ? cycler.presets[0].fogDensity : 0.016f;
                float k = density / baseDensity;
                foreach (var p in cycler.presets) p.fogDensity *= k;
                cycler.presets[0].fogColor = fogColor;
                EditorUtility.SetDirty(cycler);
            }
        }

        // ───────────── 지형 ─────────────
        static Terrain[] BuildTerrain(WorldData w, Dictionary<string, PropMeta> manifest, List<string> warnings, Stats st)
        {
            Progress("지형 층", 0.05f);
            NecroEditorUtil.EnsureFolder(GeneratedFolder + "/Layers");
            var layers = new TerrainLayer[w.layers.Count];
            bool anyNormal = false;
            for (int i = 0; i < w.layers.Count; i++)
            {
                var d = w.layers[i];
                string path = GeneratedFolder + "/Layers/" + d.name + ".terrainlayer";
                var tl = AssetDatabase.LoadAssetAtPath<TerrainLayer>(path);
                if (tl == null)
                {
                    tl = new TerrainLayer();
                    AssetDatabase.CreateAsset(tl, path);
                }
                tl.diffuseTexture = AssetDatabase.LoadAssetAtPath<Texture2D>(TerrainTexFolder + "/" + d.albedo);
                tl.normalMapTexture = d.normal != null ? AssetDatabase.LoadAssetAtPath<Texture2D>(TerrainTexFolder + "/" + d.normal) : null;
                if (tl.normalMapTexture != null) anyNormal = true;
                tl.tileSize = new Vector2(d.tile, d.tile);
                tl.tileOffset = Vector2.zero;
                tl.smoothness = d.smoothness;
                tl.metallic = 0f;
                tl.normalScale = 1f;
                EditorUtility.SetDirty(tl);
                layers[i] = tl;
            }
            st.layers = layers.Length;

            var tmat = AssetDatabase.LoadAssetAtPath<Material>(GeneratedFolder + "/TerrainLit.mat");
            if (tmat == null)
            {
                tmat = new Material(Shader.Find(TerrainShader)) { name = "TerrainLit" };
                AssetDatabase.CreateAsset(tmat, GeneratedFolder + "/TerrainLit.mat");
            }
            if (anyNormal) tmat.EnableKeyword("_NORMALMAP");
            tmat.enableInstancing = true;
            EditorUtility.SetDirty(tmat);

            // 풀 프로토타입 (detail 채널 k → 프로토타입 번호)
            var detailProtos = new List<DetailPrototype>();
            var channelToProto = new int[w.details.Count];
            for (int k = 0; k < w.details.Count; k++)
            {
                var d = w.details[k];
                channelToProto[k] = -1;
                var prefab = NecroProps.LoadPrefab(d.asset);
                if (prefab == null) continue;
                if (prefab.GetComponent<MeshFilter>() == null)
                {
                    warnings.Add("풀 " + d.asset + ": 프리팹 뿌리에 메쉬가 없어요 (manifest 의 kind 가 detail 인지 확인) → 뺐어요");
                    continue;
                }
                var dp = new DetailPrototype
                {
                    prototype = prefab,
                    usePrototypeMesh = true,
                    useInstancing = true,
                    renderMode = DetailRenderMode.VertexLit,
                    minWidth = d.minScale, maxWidth = d.maxScale,
                    minHeight = d.minScale, maxHeight = d.maxScale,
                    noiseSeed = 1000 + k * 77,
                    noiseSpread = 0.35f,
                    healthyColor = Color.white,
                    dryColor = Color.white
                };
#if UNITY_2022_2_OR_NEWER
                // META.align (지형 경사에 맞춰 눕힐지) 를 따른다: true 면 비탈에서 반쯤 기울게, false(갈대 등)는 곧게.
                // manifest 에 없으면 예전처럼 기울인다
                PropMeta dmeta;
                bool align = manifest.TryGetValue(d.asset, out dmeta) ? dmeta.align : true;
                dp.alignToGround = align ? 0.5f : 0f;
                dp.positionJitter = 1f;         // 칸 안에서 자리를 흩는다 (인스턴스 수 모드)
                dp.useDensityScaling = true;    // 품질 설정의 풀 밀도 배율을 따른다
#endif
                string err;
                if (!dp.Validate(out err)) { warnings.Add("풀 " + d.asset + ": " + err); continue; }
                channelToProto[k] = detailProtos.Count;
                detailProtos.Add(dp);
            }
            st.detailProtos = detailProtos.Count;

            // 나무 프로토타입 (trees.json 번호 → 지형 번호)
            var treeProtos = new List<TreePrototype>();
            var treeMap = new int[w.treeProtos.Count];
            var treeSink = new float[w.treeProtos.Count];
            for (int i = 0; i < w.treeProtos.Count; i++)
            {
                treeMap[i] = -1;
                var prefab = NecroProps.LoadPrefab(w.treeProtos[i]);
                if (prefab == null) continue;
                PropMeta meta;
                treeSink[i] = manifest.TryGetValue(w.treeProtos[i], out meta) ? meta.sink : 0f;
                treeMap[i] = treeProtos.Count;
                treeProtos.Add(new TreePrototype { prefab = prefab });
            }
            st.treeProtos = treeProtos.Count;

            // 타일마다 나무 나누기
            int n = w.tiles;
            float tileSize = w.TileSize;
            var tileTrees = new List<TreeInstance>[n * n];
            for (int i = 0; i < tileTrees.Length; i++) tileTrees[i] = new List<TreeInstance>();
            foreach (var t in w.trees)
            {
                int proto = treeMap[(int)t[0]];
                float x = t[1], z = t[2], yawDeg = t[3], scale = t[4];
                if (proto < 0 || x < 0f || z < 0f || x > w.size || z > w.size || scale <= 0f) { st.skippedTrees++; continue; }
                int tx, tz;
                float nx, nz;
                NecroWorldGrid.TreeTile(x, z, w.size, n, out tx, out tz, out nx, out nz);
                float y = w.HeightAt(x, z) - treeSink[(int)t[0]] * scale;         // META.sink 만큼 묻는다
                tileTrees[tz * n + tx].Add(new TreeInstance
                {
                    position = new Vector3(nx, Mathf.Clamp01(y / w.height), nz),
                    rotation = yawDeg * Mathf.Deg2Rad,                  // Unity Y 회전 (라디안)
                    widthScale = scale,
                    heightScale = scale,
                    color = new Color32(255, 255, 255, 255),
                    lightmapColor = new Color32(255, 255, 255, 255),
                    prototypeIndex = proto
                });
                st.trees++;
            }
            if (st.skippedTrees > 0) warnings.Add("지형 나무 " + st.skippedTrees + "그루를 뺐어요 (프리팹 없음 또는 지형 밖)");

            // 타일
            var parent = new GameObject("Terrain").transform;
            var terrains = new Terrain[n * n];
            int tileRes = w.TileRes, aRes = w.splatRes / n, dRes = w.detailRes / n;
            for (int tz = 0; tz < n; tz++)
                for (int tx = 0; tx < n; tx++)
                {
                    float baseT = 0.08f + 0.5f * (tz * n + tx) / (n * n);
                    string label = "지형 타일 (" + tx + ", " + tz + ") ";
                    string path = GeneratedFolder + "/Terrain_" + tx + "_" + tz + ".asset";
                    var td = AssetDatabase.LoadAssetAtPath<TerrainData>(path);
                    if (td == null)
                    {
                        td = new TerrainData();
                        AssetDatabase.CreateAsset(td, path);     // 먼저 에셋으로 만들어야 층 무게 텍스처가 함께 저장된다
                    }

                    Progress(label + "높이", baseT);
                    td.heightmapResolution = tileRes;              // 크기보다 먼저
                    td.size = new Vector3(tileSize, w.height, tileSize);
                    td.SetHeights(0, 0, NecroWorldGrid.TileHeights(w.heights, w.heightRes, n, tx, tz));

                    Progress(label + "층 무게", baseT + 0.04f);
                    td.terrainLayers = layers;
                    td.alphamapResolution = aRes;
                    td.baseMapResolution = 1024;
                    td.SetAlphamaps(0, 0, NecroWorldGrid.TileAlphamaps(w.splat0, w.splat1, w.layers.Count, w.splatRes, w.size, n, tx, tz, aRes));

                    Progress(label + "풀", baseT + 0.08f);
                    td.SetDetailResolution(dRes, 32);
                    td.detailPrototypes = detailProtos.ToArray();
#if UNITY_2022_2_OR_NEWER
                    td.SetDetailScatterMode(DetailScatterMode.InstanceCountMode);   // 칸 값 = 그 칸의 포기 수
#endif
                    for (int k = 0; k < w.details.Count; k++)
                    {
                        if (channelToProto[k] < 0) continue;
                        long sum;
                        var px = k < 4 ? w.detail0 : w.detail1;
                        td.SetDetailLayer(0, 0, channelToProto[k], NecroWorldGrid.TileDetails(px, k & 3, w.detailRes, n, tx, tz, w.details[k].maxPerCell, k, out sum));
                        st.details += sum;
                    }

                    Progress(label + "나무", baseT + 0.1f);
                    td.treePrototypes = treeProtos.ToArray();
                    td.RefreshPrototypes();
                    td.SetTreeInstances(tileTrees[tz * n + tx].ToArray(), false);   // 높이는 sink 를 반영해 직접 넣었다
                    EditorUtility.SetDirty(td);

                    var go = Terrain.CreateTerrainGameObject(td);
                    go.name = "Terrain_" + tx + "_" + tz;
                    go.transform.SetParent(parent, false);
                    go.transform.position = new Vector3(tx * tileSize, 0f, tz * tileSize);
                    var t = go.GetComponent<Terrain>();
                    SetupTerrain(t, tmat);
                    terrains[tz * n + tx] = t;
                    st.tiles++;
                }

            // 이웃 연결 (가장자리 LOD·법선이 맞게)
            for (int tz = 0; tz < n; tz++)
                for (int tx = 0; tx < n; tx++)
                {
                    Terrain left = tx > 0 ? terrains[tz * n + tx - 1] : null;
                    Terrain right = tx < n - 1 ? terrains[tz * n + tx + 1] : null;
                    Terrain top = tz < n - 1 ? terrains[(tz + 1) * n + tx] : null;      // +Z (북)
                    Terrain bottom = tz > 0 ? terrains[(tz - 1) * n + tx] : null;
                    terrains[tz * n + tx].SetNeighbors(left, top, right, bottom);
                }
            return terrains;
        }

        // 오픈월드에 맞춘 지형 설정
        static void SetupTerrain(Terrain t, Material mat)
        {
            t.materialTemplate = mat;
            t.drawInstanced = true;
            t.heightmapPixelError = 4f;          // 먼 산은 성기게
            t.basemapDistance = 400f;            // 이 너머는 미리 합친 저해상도 색
            t.detailObjectDistance = DetailDistance;   // 풀이 보이는 거리 (값과 이유는 맨 위 상수)
            t.detailObjectDensity = DetailDensity;
            t.treeDistance = 1200f;              // 카메라 먼 거리보다 짧다. 이 너머 나무는 안개에 다 덮여 능선 위의 작은 윤곽으로만 남는다
                                                 // (더 줄이면 능선 위 나무가 가까운 거리에서 보였다 사라진다)
            t.treeBillboardDistance = 1200f;     // LOD 그룹 나무는 자체 LOD 를 쓴다
            t.treeCrossFadeLength = 0f;
            t.treeMaximumFullLODCount = 400;
            t.treeLODBiasMultiplier = 1f;
            t.shadowCastingMode = ShadowCastingMode.On;
            t.reflectionProbeUsage = ReflectionProbeUsage.Off;
            t.allowAutoConnect = true;
            t.groupingID = 0;
        }

        // ───────────── 소품 ─────────────
        static Transform Cell(Dictionary<long, Transform> cells, Transform parent, Vector3 p)
        {
            int cx = Mathf.FloorToInt(p.x / CellSize), cz = Mathf.FloorToInt(p.z / CellSize);
            long key = ((long)cx << 32) ^ (uint)cz;
            Transform t;
            if (!cells.TryGetValue(key, out t))
            {
                t = new GameObject("Cell_" + cx + "_" + cz).transform;
                t.SetParent(parent, false);
                cells[key] = t;
            }
            return t;
        }

        static void BuildObjects(WorldData w, List<string> warnings, Stats st)
        {
            var root = new GameObject("Props").transform;
            var cells = new Dictionary<long, Transform>();
            var cache = new Dictionary<string, GameObject>();
            for (int i = 0; i < w.objects.Count; i++)
            {
                if (i % 200 == 0) Progress("소품 놓기 " + i + " / " + w.objects.Count, 0.6f + 0.25f * i / Mathf.Max(1, w.objects.Count));
                var o = w.objects[i];
                GameObject prefab;
                if (!cache.TryGetValue(o.a, out prefab)) { prefab = NecroProps.LoadPrefab(o.a); cache[o.a] = prefab; }
                if (prefab == null) { st.skippedObjects++; continue; }
                var go = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
                go.transform.SetParent(Cell(cells, root, o.p), false);
                go.transform.localPosition = o.p;            // 칸 부모는 원점에 있으므로 로컬 = 월드
                go.transform.localRotation = o.q;
                go.transform.localScale = Vector3.one * o.s;
                if (go.GetComponentInChildren<Light>(true) != null) st.propLights++;
                st.props++;
            }
            if (st.skippedObjects > 0) warnings.Add("소품 " + st.skippedObjects + "개를 뺐어요 (프리팹 없음)");
        }

        static void BuildLights(WorldData w, Stats st)
        {
            Progress("광원", 0.86f);
            var root = new GameObject("Lights").transform;
            var cells = new Dictionary<long, Transform>();
            foreach (var l in w.lights)
            {
                var go = new GameObject("Light");
                go.transform.SetParent(Cell(cells, root, l.p), false);
                go.transform.localPosition = l.p;
                var light = go.AddComponent<Light>();
                light.type = LightType.Point;
                light.color = l.c;
                light.intensity = l.i;
                light.range = l.r;
                light.shadows = LightShadows.None;
                if (l.far > 0f) go.AddComponent<LightCullDistance>().far = l.far;   // 등대 빛: LightCuller 가 far 에서 끈다
                if (l.flicker)
                {
                    var f = go.AddComponent<SoulFlicker>();
                    f.amount = 0.3f;
                    f.bobHeight = 0.15f;      // 도깨비불처럼 조금 떠다닌다
                }
                st.lights++;
            }
        }

        // ───────────── 물 ─────────────
        static Mesh WaterGrid()
        {
            string path = GeneratedFolder + "/WaterGrid.asset";
            var mesh = AssetDatabase.LoadAssetAtPath<Mesh>(path);
            if (mesh != null) return mesh;
            const int N = 32;     // 1 × 1 판을 32 × 32 로 나눈다 (정점 안개·광원 목록이 고르게)
            var verts = new Vector3[(N + 1) * (N + 1)];
            var uvs = new Vector2[verts.Length];
            var normals = new Vector3[verts.Length];
            for (int z = 0; z <= N; z++)
                for (int x = 0; x <= N; x++)
                {
                    int i = z * (N + 1) + x;
                    verts[i] = new Vector3(x / (float)N - 0.5f, 0f, z / (float)N - 0.5f);
                    uvs[i] = new Vector2(x / (float)N, z / (float)N);
                    normals[i] = Vector3.up;
                }
            var tris = new int[N * N * 6];
            int k = 0;
            for (int z = 0; z < N; z++)
                for (int x = 0; x < N; x++)
                {
                    int i = z * (N + 1) + x;
                    tris[k++] = i; tris[k++] = i + N + 1; tris[k++] = i + 1;
                    tris[k++] = i + 1; tris[k++] = i + N + 1; tris[k++] = i + N + 2;
                }
            mesh = new Mesh { name = "WaterGrid", vertices = verts, uv = uvs, normals = normals, triangles = tris };
            mesh.RecalculateBounds();
            AssetDatabase.CreateAsset(mesh, path);
            return mesh;
        }

        static void BuildWater(WorldData w, Stats st)
        {
            if (w.water.Count == 0) return;
            Progress("물", 0.88f);
            var mat = AssetDatabase.LoadAssetAtPath<Material>(WorldMatFolder + "/Water.mat");
            if (mat == null)
            {
                mat = new Material(Shader.Find(WaterShader)) { name = "Water" };
                var sky = RenderSettings.skybox;
                if (sky != null && sky.HasProperty("_TopColor")) mat.SetColor("_SkyTopColor", sky.GetColor("_TopColor"));
                AssetDatabase.CreateAsset(mat, WorldMatFolder + "/Water.mat");
            }
            var mesh = WaterGrid();
            var root = new GameObject("Water").transform;
            foreach (var d in w.water)
            {
                var go = new GameObject("Water Surface");
                go.transform.SetParent(root, false);
                go.transform.position = d.p;
                go.transform.rotation = Quaternion.Euler(0f, d.yaw, 0f);
                go.transform.localScale = new Vector3(Mathf.Max(0.1f, d.size.x), 1f, Mathf.Max(0.1f, d.size.y));
                go.AddComponent<MeshFilter>().sharedMesh = mesh;
                var mr = go.AddComponent<MeshRenderer>();
                mr.sharedMaterial = mat;
                mr.shadowCastingMode = ShadowCastingMode.Off;
                mr.receiveShadows = true;
                mr.lightProbeUsage = LightProbeUsage.Off;
                mr.reflectionProbeUsage = ReflectionProbeUsage.Off;
                st.water++;
            }
        }

        // ───────────── 효과 (입자) ─────────────
        // hdrLinear: tint 를 선형 HDR 값으로 보고 넣는다 (SetColor 는 감마 값으로 저장되고 선형 프로젝트에서 선형으로 바뀐다)
        static Material FxMaterial(string name, Color tint, float softness, bool hdrLinear)
        {
            string path = WorldMatFolder + "/" + name + ".mat";
            var m = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (m != null) return m;
            m = new Material(Shader.Find(ParticleShader)) { name = name };
            m.SetColor("_TintColor", hdrLinear ? tint.gamma : tint);
            m.SetFloat("_Softness", softness);
            AssetDatabase.CreateAsset(m, path);
            return m;
        }

        static Gradient FadeInOut()
        {
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                      new[] { new GradientAlphaKey(0f, 0f), new GradientAlphaKey(1f, 0.25f), new GradientAlphaKey(1f, 0.7f), new GradientAlphaKey(0f, 1f) });
            return g;
        }

        // 효과 하나. r = 퍼지는 반지름 (m), rate = 방출량 배율
        public static ParticleSystem MakeFx(string type, string name, Transform parent, Vector3 position, float r, float rate)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            go.transform.position = position;
            var ps = go.AddComponent<ParticleSystem>();
            var main = ps.main;
            main.loop = true;
            main.prewarm = true;
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.cullingMode = ParticleSystemCullingMode.Pause;      // 화면 밖에서는 멈춘다 (월드에 수백 개)
            var em = ps.emission;
            var sh = ps.shape;
            var col = ps.colorOverLifetime;
            col.enabled = true;
            col.color = new ParticleSystem.MinMaxGradient(FadeInOut());
            var pr = go.GetComponent<ParticleSystemRenderer>();
            float area = Mathf.Max(1f, r * r);

            switch (type)
            {
                case "mist":       // 바닥에 누운 큰 안개 덩어리가 천천히 흐른다
                {
                    main.startLifetime = new ParticleSystem.MinMaxCurve(14f, 24f);
                    main.startSpeed = 0f;
                    main.startSize = new ParticleSystem.MinMaxCurve(Mathf.Clamp(r * 0.35f, 4f, 9f), Mathf.Clamp(r * 0.7f, 8f, 18f));
                    main.startColor = new ParticleSystem.MinMaxGradient(new Color(1f, 1f, 1f, 0.06f), new Color(1f, 1f, 1f, 0.13f));
                    main.startRotation = new ParticleSystem.MinMaxCurve(0f, Mathf.PI * 2f);
                    main.maxParticles = (int)Mathf.Clamp(area * 0.08f, 12f, 160f);
                    em.rateOverTime = main.maxParticles / 20f * rate;
                    sh.shapeType = ParticleSystemShapeType.Box;
                    sh.scale = new Vector3(r * 2f, 0.6f, r * 2f);
                    var vel = ps.velocityOverLifetime;
                    vel.enabled = true;
                    vel.x = new ParticleSystem.MinMaxCurve(0.15f, 0.45f);
                    vel.y = new ParticleSystem.MinMaxCurve(0f, 0f);
                    vel.z = new ParticleSystem.MinMaxCurve(-0.1f, 0.1f);
                    pr.renderMode = ParticleSystemRenderMode.HorizontalBillboard;
                    pr.sharedMaterial = FxMaterial("Fx_Mist", new Color(0.5f, 0.42f, 0.85f, 1f), 1.4f, false);
                    break;
                }
                case "soulfire":   // 땅에서 피어오르는 보랏빛 영혼 불꽃
                {
                    main.startLifetime = new ParticleSystem.MinMaxCurve(0.8f, 1.8f);
                    main.startSpeed = new ParticleSystem.MinMaxCurve(0.4f, 1.4f);
                    main.startSize = new ParticleSystem.MinMaxCurve(0.12f, 0.45f);
                    main.startColor = new ParticleSystem.MinMaxGradient(new Color(0.85f, 0.55f, 1f, 0.9f), new Color(0.55f, 0.75f, 1f, 0.7f));
                    main.gravityModifier = -0.12f;
                    main.maxParticles = (int)Mathf.Clamp(area * 2f, 40f, 300f);
                    em.rateOverTime = main.maxParticles / 1.4f * rate;
                    sh.shapeType = ParticleSystemShapeType.Cone;
                    sh.angle = 8f;
                    sh.radius = Mathf.Clamp(r * 0.3f, 0.3f, 4f);
                    go.transform.rotation = Quaternion.Euler(-90f, 0f, 0f);       // 원뿔이 위로
                    var size = ps.sizeOverLifetime;
                    size.enabled = true;
                    size.size = new ParticleSystem.MinMaxCurve(1f, AnimationCurve.EaseInOut(0f, 1f, 1f, 0.1f));
                    var noise = ps.noise;
                    noise.enabled = true;
                    noise.strength = 0.4f;
                    noise.frequency = 0.8f;
                    pr.sharedMaterial = FxMaterial("Fx_Soulfire", new Color(2.2f, 0.9f, 3.6f, 1f), 2f, true);
                    break;
                }
                case "fireflies":  // 창백한 청록 반딧불: 느리게 떠다니며 깜박인다
                {
                    main.startLifetime = new ParticleSystem.MinMaxCurve(4f, 8f);
                    main.startSpeed = new ParticleSystem.MinMaxCurve(0f, 0.15f);
                    main.startSize = new ParticleSystem.MinMaxCurve(0.04f, 0.1f);
                    main.startColor = new ParticleSystem.MinMaxGradient(new Color(0.55f, 1f, 0.8f, 1f), new Color(0.45f, 0.85f, 1f, 1f));
                    main.maxParticles = (int)Mathf.Clamp(area * 0.12f, 15f, 220f);
                    em.rateOverTime = main.maxParticles / 6f * rate;
                    sh.shapeType = ParticleSystemShapeType.Box;
                    sh.scale = new Vector3(r * 2f, 2.5f, r * 2f);
                    go.transform.position = position + Vector3.up * 1.2f;
                    var noise = ps.noise;
                    noise.enabled = true;
                    noise.strength = 0.5f;
                    noise.frequency = 0.35f;
                    // 깜박임: 수명 동안 알파가 여러 번 오르내린다
                    var g = new Gradient();
                    g.SetKeys(new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                              new[] { new GradientAlphaKey(0f, 0f), new GradientAlphaKey(1f, 0.15f), new GradientAlphaKey(0.15f, 0.35f),
                                      new GradientAlphaKey(1f, 0.55f), new GradientAlphaKey(0.2f, 0.75f), new GradientAlphaKey(0f, 1f) });
                    col.color = new ParticleSystem.MinMaxGradient(g);
                    pr.sharedMaterial = FxMaterial("Fx_Firefly", new Color(0.9f, 2.2f, 1.5f, 1f), 2.5f, true);
                    break;
                }
                default:           // wisps: 떠도는 영혼 불티
                {
                    main.startLifetime = new ParticleSystem.MinMaxCurve(5f, 10f);
                    main.startSpeed = new ParticleSystem.MinMaxCurve(0.02f, 0.25f);
                    main.startSize = new ParticleSystem.MinMaxCurve(0.05f, 0.2f);
                    main.startColor = new ParticleSystem.MinMaxGradient(new Color(0.8f, 0.55f, 1f, 0.9f), new Color(0.5f, 0.7f, 1f, 0.6f));
                    main.gravityModifier = -0.015f;
                    main.maxParticles = (int)Mathf.Clamp(area * 0.3f, 30f, 500f);
                    em.rateOverTime = main.maxParticles / 8f * rate;
                    sh.shapeType = ParticleSystemShapeType.Box;
                    sh.scale = new Vector3(r * 2f, 4f, r * 2f);
                    go.transform.position = position + Vector3.up * 2f;
                    var noise = ps.noise;
                    noise.enabled = true;
                    noise.strength = 0.35f;
                    noise.frequency = 0.25f;
                    pr.sharedMaterial = FxMaterial("Fx_Wisp", new Color(1.2f, 0.7f, 2.2f, 1f), 2f, true);
                    break;
                }
            }
            return ps;
        }

        static void BuildFx(WorldData w, Stats st)
        {
            if (w.fx.Count == 0) return;
            Progress("효과", 0.9f);
            var root = new GameObject("Effects").transform;
            var cells = new Dictionary<long, Transform>();
            foreach (var f in w.fx)
            {
                MakeFx(f.type, "Fx " + f.type, Cell(cells, root, f.p), f.p, Mathf.Max(0.5f, f.r), 1f);
                st.fx++;
            }
        }

        // 주인공 주변을 따라다니는 분위기 입자 (어디서나 불티·땅안개·반딧불이 보이게)
        static void BuildAmbient(Transform player)
        {
            var go = new GameObject("Ambient (주인공 주변)");
            go.transform.position = player.position;
            var follower = go.AddComponent<AmbientFollower>();
            follower.target = player;
            MakeFx("wisps", "Soul Embers", go.transform, player.position, 32f, 0.6f);
            MakeFx("mist", "Ground Mist", go.transform, player.position, 38f, 0.8f);
            MakeFx("fireflies", "Fireflies", go.transform, player.position, 26f, 0.5f);
        }

        // 바람·광원 컬링·장소 발견
        static void BuildSystems(WorldData w, Transform player, Stats st)
        {
            var go = new GameObject("World Systems");
            var wind = go.AddComponent<NecroWind>();
            wind.hero = player;
            var culler = go.AddComponent<LightCuller>();
            culler.target = player;
            var poi = go.AddComponent<PoiDiscovery>();
            poi.hero = player;
            poi.places = w.pois.ToArray();
            poi.worldMin = w.mapMin;             // world.json map (걸어 다니는 범위 + 여유). map.png 도 같은 범위로 그린다
            poi.worldSize = w.mapSize;
            poi.mapTexture = AssetDatabase.LoadAssetAtPath<Texture2D>(MapPath);
            st.pois = w.pois.Count;
        }
    }
}
