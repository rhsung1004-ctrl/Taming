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
    // ───────────── 공통 도우미 ─────────────
    public static class NecroEditorUtil
    {
        public static void EnsureFolder(string path)
        {
            if (AssetDatabase.IsValidFolder(path)) return;
            string parent = Path.GetDirectoryName(path).Replace('\\', '/');
            EnsureFolder(parent);
            AssetDatabase.CreateFolder(parent, Path.GetFileName(path));
        }

        // "Assets/..." 경로 → 디스크 전체 경로
        public static string FullPath(string assetPath)
        {
            return Path.Combine(Path.GetDirectoryName(Application.dataPath), assetPath).Replace('\\', '/');
        }

        public static Shader FindShader(string name, bool dialog)
        {
            var s = Shader.Find(name);
            if (s == null && dialog)
                EditorUtility.DisplayDialog("셰이더를 찾을 수 없어요",
                    "'" + name + "' 셰이더가 없습니다.\nConsole 창에 빨간 셰이더 에러가 있는지 확인하고, 있으면 그 내용을 Claude에게 보내 주세요.", "확인");
            return s;
        }

        public static string Join(List<string> lines, int max)
        {
            var sb = new System.Text.StringBuilder();
            for (int i = 0; i < lines.Count && i < max; i++) sb.Append("• ").Append(lines[i]).Append('\n');
            if (lines.Count > max) sb.Append("… 외 ").Append(lines.Count - max).Append("개 (Console 에 전부 적었어요)");
            return sb.ToString();
        }
    }

    // 소품 하나의 배치·Unity 설정 (manifest.json 의 meta. Tools/BlenderKit/README.md 참고)
    public class PropMeta
    {
        public string name;
        public string kind = "prop";                 // prop / scatter / tree / detail / landmark
        public List<string> tags = new List<string>();
        public string collider = "mesh";             // mesh / box / capsule / none
        public float footprint = 0.5f;
        public float sink;
        public float tilt;
        public bool align;
        public Vector2 scale = Vector2.one;
        public float cull = 0.01f;
        public bool shadows = true;
        public bool hasLight;
        public Vector3 lightOffsetBlender;
        public Color lightColor = new Color(0.62f, 0.35f, 1f);
        public float lightIntensity = 6f;
        public float lightRange = 8f;
        public float lightFar;                       // 끄는 거리 덮어쓰기 (m, 0 = 없음). 프리팹 광원에 LightCullDistance 로 붙는다
        public Vector3 sizeBlender;
        public bool fromManifest;
        public string detail;                        // 근접 디테일 재질: stone / wood / bone / metal / none. 비면 이름·tags 로 정한다
        public string detailResolved;                // Main 재질을 만들 때 실제로 건 디테일 (요약용)

        public bool HasTag(string t) { return tags.Contains(t); }
        public bool IsDetail { get { return kind == "detail"; } }
        public bool IsTree { get { return kind == "tree"; } }

        // Blender 로컬 (x, y, z) → Unity 로컬 (−x, z, −y)  (FBX 내보내기 축 변환과 같다)
        public static Vector3 BlenderToUnityLocal(Vector3 b) { return new Vector3(-b.x, b.z, -b.y); }

        public static PropMeta Default(string name)
        {
            var m = new PropMeta { name = name };
            m.ApplyKindDefaults(null);
            return m;
        }

        // META 에 값이 없을 때 종류에 맞는 기본값
        public void ApplyKindDefaults(Dictionary<string, object> given)
        {
            if (!Given(given, "collider")) collider = IsDetail ? "none" : IsTree ? "capsule" : "mesh";
            if (!Given(given, "shadows")) shadows = !IsDetail;
            if (!Given(given, "cull")) cull = IsDetail ? 0f : kind == "landmark" ? 0.003f : IsTree ? 0.006f : 0.012f;
        }

        static bool Given(Dictionary<string, object> d, string k) { return d != null && d.ContainsKey(k) && d[k] != null; }
    }

    // 소품 폴더 가져오기 설정 자동 적용: git pull 로 새 소품이 들어와도 텍스처·FBX 설정이 맞춰진다
    public class NecroPropPostprocessor : AssetPostprocessor
    {
        void OnPreprocessTexture()
        {
            if (NecroProps.WantsTextureSettings(assetPath)) NecroProps.ConfigureTexture((TextureImporter)assetImporter, assetPath);
        }

        void OnPreprocessModel()
        {
            if (assetPath.StartsWith(NecroProps.KitFolder + "/")) NecroProps.ConfigureModel((ModelImporter)assetImporter);
        }
    }

    // Tools → Necro → 월드 → 0. 소품 가져오기 설정 + 프리팹 만들기
    public static class NecroProps
    {
        public const string KitFolder = "Assets/_Necro/Art/Environment/Graveyard";
        public const string ManifestPath = KitFolder + "/manifest.json";
        public const string AtlasPath = KitFolder + "/foliage_atlas.png";
        public const string PrefabFolder = "Assets/_Necro/Prefabs/Environment";
        public const string MatFolder = "Assets/_Necro/Art/Materials/Props";
        public const string WorldFolder = "Assets/_Necro/Art/World";
        public const string FoliageShader = "Necro/Foliage";
        const string LitShader = "Universal Render Pipeline/Lit";

        // 근접 디테일 텍스처 (Tools/BlenderKit/detailtex.py 가 만든다): detail_<종류>_albedo.png / _normal.png
        public const string DetailFolder = "Assets/_Necro/Art/Materials/Detail";
        public static readonly string[] DetailKinds = { "stone", "wood", "bone", "metal" };
        // 디테일 한 장이 덮는 실제 크기 (m). detailtex.py 의 REPEAT_M 과 같아야 무늬 크기(알갱이 1~3 mm, 구멍 2~10 mm)가 맞는다
        static readonly float[] DetailRepeat = { 0.9f, 0.75f, 0.6f, 0.6f };
        // 밉맵 fade: 이 밉 단계부터 회색(노멀은 평평)으로 옅어져 끝 단계에서 사라진다.
        // 디테일 텍셀 밀도 ≈ 1024 / 0.6~0.9 m → 1080p·시야 55° 에서 밉 3 ≈ 7 m, 밉 7 ≈ 110 m.
        // 반복 무늬가 멀리서 격자로 보이지 않고, UV 섬 경계(미분이 튀어 가장 낮은 밉을 읽는 곳)에도 티가 나지 않는다
        public const int DetailFadeStart = 3, DetailFadeEnd = 7;
        // 지난번에 자동으로 넣은 디테일 타일링 (재질 태그). 지금 값이 이것과 다르면 사람이 Inspector 에서 고친 것으로 보고 둔다
        const string DetailTilingTag = "NecroDetailTiling";

        // kit.py 의 GLOW 표와 같다: (색, 세기). HDR 선형 값 = 색 × 세기
        public static readonly string[] GlowNames = { "Glow_Soul", "Glow_Spirit", "Glow_Toxic", "Glow_Ember" };
        static readonly Color[] GlowColors =
        {
            new Color(0.55f, 0.28f, 1.0f), new Color(0.45f, 0.85f, 1.0f), new Color(0.45f, 1.0f, 0.35f), new Color(1.0f, 0.42f, 0.12f)
        };
        static readonly float[] GlowStrength = { 9f, 7f, 7f, 8f };

        // ───────────── 가져오기 설정 ─────────────
        public static bool WantsTextureSettings(string path)
        {
            return path.StartsWith(KitFolder + "/") || path.StartsWith(WorldFolder + "/") || path.StartsWith(DetailFolder + "/");
        }

        // 텍스처 가져오기 설정. 바뀐 것이 있으면 true
        public static bool ConfigureTexture(TextureImporter ti, string path)
        {
            if (path.StartsWith(DetailFolder + "/")) return ConfigureDetailTexture(ti, path);
            string file = Path.GetFileNameWithoutExtension(path).ToLowerInvariant();
            bool changed = false;
            bool isMap = path.EndsWith("/map.png");
            if (file.EndsWith("_normal"))
            {
                if (ti.textureType != TextureImporterType.NormalMap) { ti.textureType = TextureImporterType.NormalMap; changed = true; }
                if (ti.sRGBTexture) { ti.sRGBTexture = false; changed = true; }
            }
            else
            {
                if (ti.textureType != TextureImporterType.Default) { ti.textureType = TextureImporterType.Default; changed = true; }
                if (!ti.sRGBTexture) { ti.sRGBTexture = true; changed = true; }
            }

            if (file == "foliage_atlas")
            {
                // 잎 아틀라스: 알파 컷이 멀리서도 얇아지지 않게 (밉맵마다 알파 면적 유지)
                if (ti.alphaSource != TextureImporterAlphaSource.FromInput) { ti.alphaSource = TextureImporterAlphaSource.FromInput; changed = true; }
                if (!ti.alphaIsTransparency) { ti.alphaIsTransparency = true; changed = true; }
                if (!ti.mipMapsPreserveCoverage) { ti.mipMapsPreserveCoverage = true; changed = true; }
                if (Mathf.Abs(ti.alphaTestReferenceValue - 0.5f) > 0.001f) { ti.alphaTestReferenceValue = 0.5f; changed = true; }
                if (ti.wrapMode != TextureWrapMode.Clamp) { ti.wrapMode = TextureWrapMode.Clamp; changed = true; }
                if (ti.anisoLevel != 2) { ti.anisoLevel = 2; changed = true; }
            }
            else if (isMap)
            {
                if (ti.wrapMode != TextureWrapMode.Clamp) { ti.wrapMode = TextureWrapMode.Clamp; changed = true; }
                if (ti.maxTextureSize != 1024) { ti.maxTextureSize = 1024; changed = true; }
                if (ti.npotScale != TextureImporterNPOTScale.None) { ti.npotScale = TextureImporterNPOTScale.None; changed = true; }
                if (ti.textureCompression != TextureImporterCompression.CompressedHQ) { ti.textureCompression = TextureImporterCompression.CompressedHQ; changed = true; }
            }
            else
            {
                // 지형 층 텍스처는 비스듬히 보이므로 이방성 필터를 높게
                int aniso = path.StartsWith(WorldFolder + "/") ? 8 : 4;
                if (ti.anisoLevel != aniso) { ti.anisoLevel = aniso; changed = true; }
                if (ti.wrapMode != TextureWrapMode.Repeat) { ti.wrapMode = TextureWrapMode.Repeat; changed = true; }
            }
            if (!ti.mipmapEnabled) { ti.mipmapEnabled = true; changed = true; }
            if (!isMap && !ti.streamingMipmaps) { ti.streamingMipmaps = true; changed = true; }   // 오픈월드: 텍스처 스트리밍
            return changed;
        }

        // 근접 디테일 텍스처 가져오기 설정. 바뀐 것이 있으면 true
        // - 색(albedo): sRGB 끔. URP Lit 은 디테일 색을 "기본 색 × (디테일 × 2)" 로 곱한다 (URP 6000.0 LitInput.hlsl ApplyDetailAlbedo,
        //   셰이더 기본값도 "linearGrey"). 선형으로 읽어야 화소값 128 = 0.5 → ×2 = 1 (그대로). sRGB 로 읽으면 0.5 가 0.21 이 되어 소품이 반쯤 어두워진다
        // - 노멀: Normal map 형식 (OpenGL, 초록 = 위 — Unity 와 같다). sRGB 는 형식이 끈다
        // - 반복(Repeat), 밉맵 fade, 삼선형·이방성 필터 (비스듬히 보이는 벽·바닥에서도 흐려지지 않게)
        // - 압축 고품질: 0.5 둘레 ±5% 의 낮은 대비라 일반 압축(DXT1)의 색 단계·초록 틀어짐이 ×2 로 커져 보인다
        // - 스트리밍 끔: 모든 소품이 함께 쓰는 작은 텍스처라 늘 올려 둔다
        static bool ConfigureDetailTexture(TextureImporter ti, string path)
        {
            bool changed = false;
            bool normal = Path.GetFileNameWithoutExtension(path).ToLowerInvariant().EndsWith("_normal");
            var type = normal ? TextureImporterType.NormalMap : TextureImporterType.Default;
            if (ti.textureType != type) { ti.textureType = type; changed = true; }
            if (ti.sRGBTexture) { ti.sRGBTexture = false; changed = true; }
            if (ti.wrapMode != TextureWrapMode.Repeat) { ti.wrapMode = TextureWrapMode.Repeat; changed = true; }
            if (!ti.mipmapEnabled) { ti.mipmapEnabled = true; changed = true; }
            if (!ti.fadeout) { ti.fadeout = true; changed = true; }
            if (ti.mipmapFadeDistanceStart != DetailFadeStart) { ti.mipmapFadeDistanceStart = DetailFadeStart; changed = true; }
            if (ti.mipmapFadeDistanceEnd != DetailFadeEnd) { ti.mipmapFadeDistanceEnd = DetailFadeEnd; changed = true; }
            if (ti.filterMode != FilterMode.Trilinear) { ti.filterMode = FilterMode.Trilinear; changed = true; }
            if (ti.anisoLevel != 8) { ti.anisoLevel = 8; changed = true; }
            if (ti.textureCompression != TextureImporterCompression.CompressedHQ) { ti.textureCompression = TextureImporterCompression.CompressedHQ; changed = true; }
            if (ti.streamingMipmaps) { ti.streamingMipmaps = false; changed = true; }
            return changed;
        }

        // FBX 가져오기 설정: 정적 배경 모델 (애니메이션·카메라·조명 끔). 바뀐 것이 있으면 true
        public static bool ConfigureModel(ModelImporter mi)
        {
            bool changed = false;
            if (mi.importAnimation) { mi.importAnimation = false; changed = true; }
            if (mi.animationType != ModelImporterAnimationType.None) { mi.animationType = ModelImporterAnimationType.None; changed = true; }
            if (mi.importCameras) { mi.importCameras = false; changed = true; }
            if (mi.importLights) { mi.importLights = false; changed = true; }
            if (mi.importBlendShapes) { mi.importBlendShapes = false; changed = true; }
            if (mi.importVisibility) { mi.importVisibility = false; changed = true; }
            if (mi.importConstraints) { mi.importConstraints = false; changed = true; }
            if (mi.addCollider) { mi.addCollider = false; changed = true; }
            if (mi.generateSecondaryUV) { mi.generateSecondaryUV = false; changed = true; }
            if (mi.importNormals != ModelImporterNormals.Import) { mi.importNormals = ModelImporterNormals.Import; changed = true; }
            // Blender 노멀맵은 MikkTSpace 로 구웠다
            if (mi.importTangents != ModelImporterTangents.CalculateMikk) { mi.importTangents = ModelImporterTangents.CalculateMikk; changed = true; }
            if (mi.meshCompression != ModelImporterMeshCompression.Off) { mi.meshCompression = ModelImporterMeshCompression.Off; changed = true; }
            return changed;
        }

        // ───────────── 목록(manifest.json) ─────────────
        public static Dictionary<string, PropMeta> LoadManifest(List<string> warnings)
        {
            var result = new Dictionary<string, PropMeta>();
            string full = NecroEditorUtil.FullPath(ManifestPath);
            if (!File.Exists(full))
            {
                if (warnings != null) warnings.Add("manifest.json 이 없어 META 없이 기본값(일반 소품, 메쉬 충돌)으로 만들었어요");
                return result;
            }
            Dictionary<string, object> root;
            try { root = NecroJson.Parse(File.ReadAllText(full)) as Dictionary<string, object>; }
            catch (System.Exception e)
            {
                if (warnings != null) warnings.Add("manifest.json 을 읽지 못했어요: " + e.Message);
                return result;
            }
            if (root == null) return result;
            var ctx = new JsonReadContext("manifest.json");
            foreach (var kv in root)
            {
                var entry = kv.Value as Dictionary<string, object>;
                if (entry == null) continue;
                var m = new PropMeta { name = kv.Key, fromManifest = true };
                var size = ctx.Floats(entry, "size", 3, kv.Key, false);
                if (size != null) m.sizeBlender = new Vector3(size[0], size[1], size[2]);
                Dictionary<string, object> meta = null;
                object mo;
                if (entry.TryGetValue("meta", out mo)) meta = mo as Dictionary<string, object>;
                if (meta != null)
                {
                    string where = kv.Key + ".meta";
                    m.kind = ctx.Str(meta, "kind", where, "prop", false).ToLowerInvariant();
                    var tags = ctx.Arr(meta, "tags", where, false);
                    if (tags != null) foreach (var t in tags) if (t is string) m.tags.Add((string)t);
                    m.collider = ctx.Str(meta, "collider", where, m.collider, false).ToLowerInvariant();
                    m.footprint = (float)ctx.Num(meta, "footprint", where, m.footprint, false);
                    m.sink = (float)ctx.Num(meta, "sink", where, 0, false);
                    m.tilt = (float)ctx.Num(meta, "tilt", where, 0, false);
                    m.align = ctx.Bool(meta, "align", false);
                    var sc = ctx.Floats(meta, "scale", 2, where, false);
                    if (sc != null) m.scale = new Vector2(sc[0], sc[1]);
                    m.cull = (float)ctx.Num(meta, "cull", where, m.cull, false);
                    m.shadows = ctx.Bool(meta, "shadows", true);
                    string dk = ctx.Str(meta, "detail", where, null, false);
                    if (dk != null) m.detail = dk.Trim().ToLowerInvariant();
                    object lo;
                    if (meta.TryGetValue("light", out lo) && lo is Dictionary<string, object>)
                    {
                        var light = (Dictionary<string, object>)lo;
                        m.hasLight = true;
                        m.lightOffsetBlender = ctx.Vec3(light, "offset", where + ".light", Vector3.zero, false);
                        m.lightColor = ctx.Col(light, "color", where + ".light", m.lightColor, false);
                        m.lightIntensity = (float)ctx.Num(light, "intensity", where + ".light", m.lightIntensity, false);
                        m.lightRange = (float)ctx.Num(light, "range", where + ".light", m.lightRange, false);
                        m.lightFar = Mathf.Max(0f, (float)ctx.Num(light, "far", where + ".light", 0, false));
                    }
                }
                m.ApplyKindDefaults(meta);
                result[kv.Key] = m;
            }
            if (warnings != null) warnings.AddRange(ctx.errors);
            return result;
        }

        // ───────────── 찾기 ─────────────
        public static string PrefabPath(string name) { return PrefabFolder + "/" + name + ".prefab"; }
        public static GameObject LoadPrefab(string name) { return AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath(name)); }
        public static GameObject LoadModel(string name) { return AssetDatabase.LoadAssetAtPath<GameObject>(KitFolder + "/" + name + ".fbx"); }

        // 새 버전(jpg)을 먼저, 없으면 이전 버전(png)
        public static Texture2D FindTexture(string folder, string baseName)
        {
            var t = AssetDatabase.LoadAssetAtPath<Texture2D>(folder + "/" + baseName + ".jpg");
            if (t == null) t = AssetDatabase.LoadAssetAtPath<Texture2D>(folder + "/" + baseName + ".png");
            return t;
        }

        public static List<string> ModelNames()
        {
            var names = new List<string>();
            string full = NecroEditorUtil.FullPath(KitFolder);
            if (!Directory.Exists(full)) return names;
            foreach (var f in Directory.GetFiles(full))
                if (f.EndsWith(".fbx", System.StringComparison.OrdinalIgnoreCase)) names.Add(Path.GetFileNameWithoutExtension(f));
            names.Sort(System.StringComparer.Ordinal);
            return names;
        }

        // ───────────── 재질 ─────────────
        static Material GetOrCreate(string path, string shaderName, System.Action<Material> onCreate)
        {
            NecroEditorUtil.EnsureFolder(Path.GetDirectoryName(path).Replace('\\', '/'));
            var m = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (m != null) return m;
            var sh = Shader.Find(shaderName);
            if (sh == null) return null;
            m = new Material(sh) { name = Path.GetFileNameWithoutExtension(path) };
            if (onCreate != null) onCreate(m);
            AssetDatabase.CreateAsset(m, path);
            return m;
        }

        // 굽기 텍스처 재질 (URP Lit + 알베도 + 노멀 + 근접 디테일). 이미 있으면 직접 조정한 값은 두고 텍스처만 새 것으로 바꾼다.
        // meta 가 없으면 (룩 장면 도구처럼 프리팹 없이 모델만 놓을 때) manifest.json 에서 찾는다 → 프리팹 경로와 같은 디테일이 걸린다
        public static Material MainMaterial(string name, PropMeta meta = null, List<string> warnings = null)
        {
            var m = GetOrCreate(MatFolder + "/" + name + ".mat", LitShader, x =>
            {
                x.SetColor("_BaseColor", Color.white);
                x.SetFloat("_Smoothness", 0.12f);
                x.enableInstancing = true;
            });
            if (m == null) return null;
            var albedo = FindTexture(KitFolder, name + "_albedo");
            var normal = AssetDatabase.LoadAssetAtPath<Texture2D>(KitFolder + "/" + name + "_normal.png");
            if (albedo != null && m.GetTexture("_BaseMap") != albedo) { m.SetTexture("_BaseMap", albedo); EditorUtility.SetDirty(m); }
            if (normal != null && m.GetTexture("_BumpMap") != normal)
            {
                m.SetTexture("_BumpMap", normal);
                m.EnableKeyword("_NORMALMAP");
                EditorUtility.SetDirty(m);
            }
            if (meta == null) meta = FindMeta(name);
            meta.detailResolved = ApplyDetail(m, meta, warnings);
            return m;
        }

        // manifest.json 을 한 번 읽어 두고 (파일이 바뀌면 다시 읽는다) 이름으로 META 를 찾는다. 없으면 기본값
        static Dictionary<string, PropMeta> metaCache;
        static System.DateTime metaCacheTime;
        public static PropMeta FindMeta(string name)
        {
            string full = NecroEditorUtil.FullPath(ManifestPath);
            var t = File.Exists(full) ? File.GetLastWriteTimeUtc(full) : System.DateTime.MinValue;
            if (metaCache == null || t != metaCacheTime)
            {
                metaCache = LoadManifest(null);
                metaCacheTime = t;
            }
            PropMeta m;
            return metaCache.TryGetValue(name, out m) ? m : PropMeta.Default(name);
        }

        // ───────────── 근접 디테일 (URP Lit Detail Inputs) ─────────────
        // 굽힌 텍스처는 텍셀 하나가 2~6 mm (큰 구조물은 1~14 cm) 라 가까이 가면 흐리다.
        // 이어 붙는 잔무늬(돌 알갱이·구멍, 나무 결, 뼈 잔금, 쇠 녹)를 URP Lit 의 Detail 로 겹친다. URP 6000.0 소스 기준:
        // - 셰이더: Lit.shader 의 _DetailMask·_DetailAlbedoMap·_DetailAlbedoMapScale·_DetailNormalMap·_DetailNormalMapScale,
        //   키워드 _DETAIL_MULX2 / _DETAIL_SCALED (ForwardLit·GBuffer·DepthNormals·Meta 패스)
        // - UV: 디테일 UV = (UV0 × _BaseMap_ST) × _DetailAlbedoMap_ST. 디테일 노멀도 _DetailAlbedoMap_ST 를 같이 쓴다 (_DetailNormalMap_ST 는 쓰지 않는다)
        // - 색: 기본 색 × (디테일 × 2) (MULX2). 노멀: BlendNormalRNM 으로 겹친다. 마스크는 _DetailMask 의 알파 (기본 흰색 = 전체)
        // 디테일 종류: META "detail" 이 있으면 그것, 없으면 이름 → tags 순으로 정한다. 확실하지 않으면 stone
        public static string DetailKindFor(PropMeta meta, List<string> warnings)
        {
            if (!string.IsNullOrEmpty(meta.detail))
            {
                if (meta.detail == "none" || System.Array.IndexOf(DetailKinds, meta.detail) >= 0) return meta.detail;
                if (warnings != null) warnings.Add(meta.name + ": META detail '" + meta.detail + "' 를 몰라 이름·tags 로 정했어요 (stone / wood / bone / metal / none)");
            }
            if (meta.IsDetail) return "none";                       // 지형 풀: 작고 수가 많아 디테일을 걸지 않는다
            string n = (meta.name ?? "").ToLowerInvariant();
            // 1) 이름 (가장 구체적). 버섯·초(밀랍)는 돌·나무 무늬가 어울리지 않아 걸지 않는다
            if (NameHas(n, "mushroom", "lotus", "candle")) return "none";
            if (NameHas(n, "lantern", "iron", "cage", "chain", "anvil", "sword", "bell")) return "metal";
            if (NameHas(n, "bone", "skull", "dragon", "rib", "spine", "claw", "skeleton")) return "bone";
            if (NameHas(n, "tree", "stump", "log", "root", "coffin", "cart", "plank", "wood", "branch", "barrel", "crate")) return "wood";
            if (NameHas(n, "grave", "ruin", "rock", "cliff", "statue", "pillar", "wall", "stair", "altar", "crypt", "tomb", "obelisk", "rubble")) return "stone";
            // 2) tags. fence·fence_gate 는 돌 기둥 + 쇠창살이라 ruin → stone
            if (meta.HasTag("bone")) return "bone";
            if (meta.HasTag("rock") || meta.HasTag("cliff") || meta.HasTag("grave") || meta.HasTag("ruin") || meta.HasTag("landmark")) return "stone";
            if (meta.HasTag("nature")) return "wood";
            return "stone";
        }

        static bool NameHas(string n, params string[] keys)
        {
            foreach (var k in keys) if (n.Contains(k)) return true;
            return false;
        }

        static float DetailRepeatFor(string kind)
        {
            int i = System.Array.IndexOf(DetailKinds, kind);
            return i >= 0 ? DetailRepeat[i] : 0.8f;
        }

        static bool IsAutoDetail(Texture t)
        {
            return t == null || AssetDatabase.GetAssetPath(t).StartsWith(DetailFolder + "/");
        }

        // Main 재질에 디테일을 건다. 걸린 종류("stone"…, "none", 사람이 직접 넣은 것은 "custom")를 돌려준다.
        // 다시 눌러도 같은 결과:
        // - Detail 폴더 밖의 텍스처를 사람이 Inspector 에서 넣었으면 그 재질의 디테일은 건드리지 않는다
        // - 타일링은 지난번에 자동으로 넣은 값(재질 태그)과 지금 값이 같을 때만 새로 계산한 값으로 바꾼다 (사람이 고친 값은 둔다)
        // - 세기(Scale 두 개)는 처음 걸 때만 1 로 맞춘다. 키워드는 URP Inspector 와 같은 규칙으로 늘 다시 맞춘다
        static string ApplyDetail(Material m, PropMeta meta, List<string> warnings)
        {
            if (!m.HasProperty("_DetailAlbedoMap") || !m.HasProperty("_DetailNormalMap")) return null;   // URP Lit 이 아닌 재질
            var curA = m.GetTexture("_DetailAlbedoMap");
            var curN = m.GetTexture("_DetailNormalMap");
            if (!IsAutoDetail(curA) || !IsAutoDetail(curN)) return "custom";

            string kind = DetailKindFor(meta, warnings);
            Texture2D a = null, n = null;
            if (kind != "none")
            {
                a = AssetDatabase.LoadAssetAtPath<Texture2D>(DetailFolder + "/detail_" + kind + "_albedo.png");
                n = AssetDatabase.LoadAssetAtPath<Texture2D>(DetailFolder + "/detail_" + kind + "_normal.png");
                if (a == null || n == null)
                {
                    if (warnings != null && !missingDetailWarned)
                        warnings.Add("근접 디테일 텍스처(" + DetailFolder + "/detail_" + kind + "_*.png)가 없어 디테일 없이 만들었어요 " +
                                     "(Git Bash 에서 git lfs pull, 또는 python3 Tools/BlenderKit/detailtex.py)");
                    missingDetailWarned = true;
                    a = n = null;
                    kind = "none";
                }
            }

            bool dirty = false;
            bool attach = a != null && curA == null && curN == null;      // 이번에 처음 건다
            if (curA != a) { m.SetTexture("_DetailAlbedoMap", a); dirty = true; }
            if (curN != n) { m.SetTexture("_DetailNormalMap", n); dirty = true; }
            string lastTag = m.GetTag(DetailTilingTag, false, "");
            if (a != null)
            {
                if (attach)
                {
                    m.SetFloat("_DetailAlbedoMapScale", 1f);      // 1 이면 _DETAIL_MULX2 (가장 가볍다). 세기는 텍스처에 구워 두었다
                    m.SetFloat("_DetailNormalMapScale", 1f);
                    dirty = true;
                }
                float tiling = DetailTiling(meta, kind);
                Vector2 cur = m.GetTextureScale("_DetailAlbedoMap");
                float last;
                bool userTuned = !attach && float.TryParse(lastTag, System.Globalization.NumberStyles.Float,
                                                           System.Globalization.CultureInfo.InvariantCulture, out last)
                                 && (Mathf.Abs(cur.x - last) > 0.005f || Mathf.Abs(cur.y - last) > 0.005f);
                if (!userTuned)
                {
                    if (cur.x != tiling || cur.y != tiling) { m.SetTextureScale("_DetailAlbedoMap", new Vector2(tiling, tiling)); dirty = true; }
                    string t = tiling.ToString("0.##", System.Globalization.CultureInfo.InvariantCulture);
                    if (lastTag != t) { m.SetOverrideTag(DetailTilingTag, t); dirty = true; }
                }
            }
            else if (lastTag != "") { m.SetOverrideTag(DetailTilingTag, ""); dirty = true; }
            if (SetDetailKeywords(m)) dirty = true;
            if (dirty) EditorUtility.SetDirty(m);
            return kind;
        }
        static bool missingDetailWarned;

        // URP 6000.0 LitDetailGUI.SetMaterialKeywords 와 같은 규칙 (Inspector 를 열면 URP 가 이 규칙으로 다시 맞추므로 같아야 한다):
        // 디테일 텍스처(색 또는 노멀)가 있으면, 색 Scale 이 1 일 때 _DETAIL_MULX2, 1 이 아니면 _DETAIL_SCALED. 없으면 둘 다 끈다
        static bool SetDetailKeywords(Material m)
        {
            bool has = m.GetTexture("_DetailAlbedoMap") != null || m.GetTexture("_DetailNormalMap") != null;
            bool scaled = m.HasProperty("_DetailAlbedoMapScale") && m.GetFloat("_DetailAlbedoMapScale") != 1f;
            bool changed = SetKeyword(m, "_DETAIL_MULX2", has && !scaled);
            changed |= SetKeyword(m, "_DETAIL_SCALED", has && scaled);
            return changed;
        }

        static bool SetKeyword(Material m, string keyword, bool on)
        {
            if (m.IsKeywordEnabled(keyword) == on) return false;
            if (on) m.EnableKeyword(keyword); else m.DisableKeyword(keyword);
            return true;
        }

        // 디테일 타일링 = (UV 1 단위가 덮는 실제 길이 m) / (디테일 한 장의 실제 크기 m) → 실제 크기로 0.6~0.9 m 에 한 번 반복.
        // 근거: kit.py 는 smart_project 로 UV 를 편다. smart_project 는 섬마다 크기를 따로 맞추지 않고 실제 크기 비율 그대로 [0,1] 에 담으므로
        // 한 소품 안에서는 텍셀 밀도가 거의 고르다 (큰 구조물의 unwrap_smoothed 는 부드럽게 한 사본을 펴서 조금 흩어진다).
        // 그래서 LOD0 Main 면의 √(실제 면적 / UV 면적) 이 곧 "UV 1 = 몇 m" 이고, 섬이 조금씩 다르므로 면적 가중 중앙값을 쓴다.
        // Blender 로 잰 값 (2026-11, 62종): 묘비 1.9 m, 바위 3.6 m, 고목 14 m, 절벽 29 m, 성당 300 m —
        // 같은 해상도라도 텍셀 밀도가 7~1600 px/m 로 크게 달라 "크기·해상도" 만으로 짐작하면 몇 배씩 틀린다 (섬 채움률이 3~65 %).
        // 메쉬를 못 읽을 때만 manifest 크기로 짐작한다 (상자 겉넓이 × 0.6 을 UV 채움률 0.45 로 나눈 값).
        public static float DetailTiling(PropMeta meta, string kind)
        {
            float mPerUv = MetersPerUv(LoadModel(meta.name));
            if (mPerUv <= 0f)
            {
                Vector3 s = meta.sizeBlender;
                float area = 2f * (s.x * s.y + s.y * s.z + s.z * s.x) * 0.6f;
                mPerUv = area > 0f ? Mathf.Sqrt(area / 0.45f) : 2f;
            }
            float tiling = Mathf.Clamp(mPerUv / DetailRepeatFor(kind), 0.25f, 2000f);
            return Mathf.Round(tiling * 100f) / 100f;
        }

        // LOD0 의 Main 면 (Glow·Foliage 슬롯 제외): 삼각형마다 √(실제 면적 / UV0 면적) 의 면적 가중 중앙값. 못 재면 0
        public static float MetersPerUv(GameObject model)
        {
            if (model == null) return 0f;
            var r = FindLod0Renderer(model, model.name);
            var mf = r != null ? r.GetComponent<MeshFilter>() : null;
            var mesh = mf != null ? mf.sharedMesh : null;
            if (mesh == null) return 0f;
            Vector3[] v = mesh.vertices;                 // 에디터에서는 읽기 가능 설정과 상관없이 읽힌다
            Vector2[] uv = mesh.uv;
            if (v.Length == 0 || uv.Length != v.Length) return 0f;
            Matrix4x4 mtx = model.transform.worldToLocalMatrix * r.transform.localToWorldMatrix;
            for (int i = 0; i < v.Length; i++) v[i] = mtx.MultiplyPoint3x4(v[i]);
            var mats = r.sharedMaterials;
            var samples = new List<Vector2>();           // (비율, 실제 면적)
            float total = 0f;
            for (int sub = 0; sub < mesh.subMeshCount; sub++)
            {
                string mn = sub < mats.Length && mats[sub] != null ? mats[sub].name : "";
                if (mn.StartsWith("Glow") || mn.StartsWith("Foliage")) continue;
                int[] tri = mesh.GetTriangles(sub);
                for (int t = 0; t + 2 < tri.Length; t += 3)
                {
                    int i0 = tri[t], i1 = tri[t + 1], i2 = tri[t + 2];
                    float wa = Vector3.Cross(v[i1] - v[i0], v[i2] - v[i0]).magnitude * 0.5f;
                    Vector2 e1 = uv[i1] - uv[i0], e2 = uv[i2] - uv[i0];
                    float ua = Mathf.Abs(e1.x * e2.y - e1.y * e2.x) * 0.5f;
                    if (wa < 1e-8f || ua < 1e-12f) continue;
                    samples.Add(new Vector2(Mathf.Sqrt(wa / ua), wa));
                    total += wa;
                }
            }
            if (samples.Count == 0 || total <= 0f) return 0f;
            samples.Sort((p, q) => p.x.CompareTo(q.x));
            float acc = 0f;
            foreach (var s in samples)
            {
                acc += s.y;
                if (acc >= total * 0.5f) return s.x;
            }
            return samples[samples.Count - 1].x;
        }

        public static Material GlowMaterial(string glowName)
        {
            int k = System.Array.IndexOf(GlowNames, glowName);
            if (k < 0) k = 0;
            Color c = GlowColors[k];
            float s = GlowStrength[k];
            return GetOrCreate(MatFolder + "/" + GlowNames[k] + ".mat", LitShader, m =>
            {
                m.SetColor("_BaseColor", c * 0.3f);
                m.SetFloat("_Smoothness", 0.4f);
                // SetColor 값은 감마 공간으로 저장되고 선형 프로젝트에서 선형으로 바뀐다 → 선형 값 (색 × 세기)이 되도록 감마로 넣는다
                Color hdr = new Color(c.r * s, c.g * s, c.b * s, 1f);
                m.SetColor("_EmissionColor", hdr.gamma);
                m.EnableKeyword("_EMISSION");
                m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
                m.enableInstancing = true;
            });
        }

        public static Material FoliageMaterial()
        {
            var m = GetOrCreate(MatFolder + "/Foliage.mat", FoliageShader, x =>
            {
                x.SetFloat("_Cutoff", 0.5f);
                x.enableInstancing = true;     // 지형 풀(인스턴싱 메쉬)에 꼭 필요
            });
            if (m == null) return null;
            var atlas = AssetDatabase.LoadAssetAtPath<Texture2D>(AtlasPath);
            if (atlas != null && m.GetTexture("_BaseMap") != atlas) { m.SetTexture("_BaseMap", atlas); EditorUtility.SetDirty(m); }
            if (!m.enableInstancing) { m.enableInstancing = true; EditorUtility.SetDirty(m); }
            return m;
        }

        // 지형 풀이 보이는 거리 (m). 월드 빌더의 Terrain.detailObjectDistance 와 지형 풀 전용 재질의 거리 축소가 함께 쓴다
        public const float TerrainDetailDistance = 70f;

        // 지형 풀(kind = detail) 전용 재질: Foliage 와 같고, 풀이 끊기는 거리 조금 앞에서 포기를 오그라뜨려 경계를 감춘다.
        // 소품의 덩굴·이끼(Foliage.mat)는 거리 축소를 쓰지 않으므로 재질을 나눈다
        public static Material FoliageDetailMaterial()
        {
            var m = GetOrCreate(MatFolder + "/Foliage_Detail.mat", FoliageShader, x =>
            {
                x.SetFloat("_Cutoff", 0.5f);
                x.enableInstancing = true;
            });
            if (m == null) return null;
            bool dirty = false;
            var atlas = AssetDatabase.LoadAssetAtPath<Texture2D>(AtlasPath);
            if (atlas != null && m.GetTexture("_BaseMap") != atlas) { m.SetTexture("_BaseMap", atlas); dirty = true; }
            if (!m.enableInstancing) { m.enableInstancing = true; dirty = true; }
            float start = TerrainDetailDistance * 0.7f, end = TerrainDetailDistance * 0.96f;
            if (m.HasProperty("_FadeStart") && (m.GetFloat("_FadeStart") != start || m.GetFloat("_FadeEnd") != end))
            {
                m.SetFloat("_FadeStart", start);
                m.SetFloat("_FadeEnd", end);
                dirty = true;
            }
            if (dirty) EditorUtility.SetDirty(m);
            return m;
        }

        // 재질 슬롯 이름으로 고른다. Blender 가 붙인 ".001" 같은 접미사가 있으므로 접두어로 비교
        public static Material PickMaterial(string slotName, Material main, List<string> warnings, string owner)
        {
            string n = slotName ?? "";
            foreach (var g in GlowNames) if (n.StartsWith(g)) return GlowMaterial(g);
            if (n.StartsWith("Glow")) return GlowMaterial("Glow_Soul");          // 이전 버전 소품: "Glow" 하나
            if (n.StartsWith("Foliage")) return FoliageMaterial();
            if (!n.StartsWith("Main") && warnings != null)
                warnings.Add(owner + ": 알 수 없는 재질 슬롯 '" + n + "' → Main 재질을 씌웠어요");
            return main;
        }

        // ───────────── 메뉴 ─────────────
        [MenuItem("Tools/Necro/월드/0. 소품 가져오기 설정 + 프리팹 만들기", priority = 100)]
        public static void BuildAllMenu()
        {
            if (NecroEditorUtil.FindShader(FoliageShader, true) == null) return;
            if (NecroEditorUtil.FindShader(LitShader, true) == null) return;
            if (ModelNames().Count == 0)
            {
                EditorUtility.DisplayDialog("소품 가져오기", KitFolder + " 폴더에 소품 모델(.fbx)이 없어요.\nGit Bash 에서 git lfs pull 을 실행했는지 확인해 주세요.", "확인");
                return;
            }
            var warnings = new List<string>();
            var counts = BuildAll(warnings);
            string summary = "[Necro] 소품 프리팹 " + counts.prefabs + "개 (일반 " + counts.props + ", 지형 나무 " + counts.trees +
                             ", 지형 풀 " + counts.details + ", 광원 포함 " + counts.lights + ") — " + PrefabFolder +
                             "\n근접 디테일 재질: " + counts.detail + " (" + DetailFolder + ")" +
                             "\n가져오기 설정을 고친 파일: 텍스처 " + counts.textures + ", 모델 " + counts.models +
                             "\n걸린 시간 " + counts.seconds.ToString("0.0") + "초" + (warnings.Count > 0 ? ", 경고 " + warnings.Count + "개" : "");
            Debug.Log(summary);
            if (warnings.Count > 0) Debug.LogWarning("[Necro] 소품 프리팹 경고\n" + string.Join("\n", warnings.ToArray()));
        }

        public struct BuildCounts { public int prefabs, props, trees, details, lights, textures, models; public float seconds; public string detail; }

        // "돌 30 · 나무 8 …" (Main 재질이 있는 소품만. 직접 넣은 디테일은 '직접')
        static string DetailSummary(List<string> names, Dictionary<string, PropMeta> manifest)
        {
            string[] keys = { "stone", "wood", "bone", "metal", "none", "custom" };
            string[] labels = { "돌", "나무", "뼈", "쇠", "없음", "직접" };
            var n = new int[keys.Length];
            foreach (var name in names)
            {
                PropMeta m;
                if (!manifest.TryGetValue(name, out m) || m.detailResolved == null) continue;
                int i = System.Array.IndexOf(keys, m.detailResolved);
                if (i >= 0) n[i]++;
            }
            var parts = new List<string>();
            for (int i = 0; i < keys.Length; i++) if (n[i] > 0) parts.Add(labels[i] + " " + n[i]);
            return parts.Count > 0 ? string.Join(" · ", parts.ToArray()) : "없음";
        }

        public static BuildCounts BuildAll(List<string> warnings)
        {
            var sw = Stopwatch.StartNew();
            var counts = new BuildCounts();
            // 소품 폴더가 없거나 모델이 하나도 없으면 아무것도 만들지 않는다 (1번 메뉴에서 바로 불려도 예외로 멈추지 않게)
            if (ModelNames().Count == 0)
            {
                warnings.Add(KitFolder + " 폴더에 소품 모델(.fbx)이 없어 프리팹을 만들지 못했어요 (Git Bash 에서 git lfs pull 을 했는지 확인해 주세요)");
                return counts;
            }
            NecroEditorUtil.EnsureFolder(PrefabFolder);
            NecroEditorUtil.EnsureFolder(MatFolder);
            try
            {
                // 1. 가져오기 설정 (바뀐 것만 다시 가져온다)
                EditorUtility.DisplayProgressBar("소품 가져오기", "텍스처·모델 가져오기 설정", 0f);
                missingDetailWarned = false;
                var reimport = new List<AssetImporter>();
                // 소품 폴더 + 근접 디테일 텍스처 폴더 (이전에 다른 설정으로 가져온 것도 바로잡는다)
                foreach (string folder in new[] { KitFolder, DetailFolder })
                {
                    string full = NecroEditorUtil.FullPath(folder);
                    if (!Directory.Exists(full)) continue;
                    foreach (var f in Directory.GetFiles(full))
                    {
                        string ext = Path.GetExtension(f).ToLowerInvariant();
                        string assetPath = folder + "/" + Path.GetFileName(f);
                        if (ext == ".png" || ext == ".jpg" || ext == ".jpeg")
                        {
                            var ti = AssetImporter.GetAtPath(assetPath) as TextureImporter;
                            if (ti != null && ConfigureTexture(ti, assetPath)) { reimport.Add(ti); counts.textures++; }
                        }
                        else if (ext == ".fbx")
                        {
                            var mi = AssetImporter.GetAtPath(assetPath) as ModelImporter;
                            if (mi != null && ConfigureModel(mi)) { reimport.Add(mi); counts.models++; }
                        }
                    }
                }
                if (reimport.Count > 0)
                {
                    AssetDatabase.StartAssetEditing();
                    try { foreach (var imp in reimport) imp.SaveAndReimport(); }
                    finally { AssetDatabase.StopAssetEditing(); }
                }

                // 2. 공용 재질
                var manifest = LoadManifest(warnings);
                if (AssetDatabase.LoadAssetAtPath<Texture2D>(AtlasPath) == null && ManifestHasFoliage(manifest))
                    warnings.Add("잎 아틀라스(" + AtlasPath + ")가 없어요. 풀·덩굴이 흰 판으로 보일 수 있어요");
                foreach (var g in GlowNames) GlowMaterial(g);
                FoliageMaterial();

                // 3. 프리팹
                var names = ModelNames();
                for (int i = 0; i < names.Count; i++)
                {
                    string name = names[i];
                    EditorUtility.DisplayProgressBar("소품 가져오기", "프리팹 만들기: " + name + " (" + (i + 1) + "/" + names.Count + ")", (i + 1f) / names.Count);
                    PropMeta meta;
                    if (!manifest.TryGetValue(name, out meta))
                    {
                        meta = PropMeta.Default(name);
                        if (manifest.Count > 0) warnings.Add(name + ": manifest.json 에 없어 기본값으로 만들었어요");
                    }
                    bool light;
                    if (BuildPrefab(name, meta, warnings, out light))
                    {
                        counts.prefabs++;
                        if (meta.IsTree) counts.trees++;
                        else if (meta.IsDetail) counts.details++;
                        else counts.props++;
                        if (light) counts.lights++;
                    }
                }
                foreach (var kv in manifest)
                    if (!names.Contains(kv.Key)) warnings.Add(kv.Key + ": manifest.json 에는 있는데 .fbx 가 없어요");
                counts.detail = DetailSummary(names, manifest);
                AssetDatabase.SaveAssets();
            }
            finally
            {
                EditorUtility.ClearProgressBar();
            }
            counts.seconds = (float)sw.Elapsed.TotalSeconds;
            return counts;
        }

        static bool ManifestHasFoliage(Dictionary<string, PropMeta> manifest)
        {
            foreach (var kv in manifest) if (kv.Value.IsDetail || kv.Value.HasTag("foliage")) return true;
            return false;
        }

        // ───────────── 프리팹 하나 ─────────────
        public static bool BuildPrefab(string name, PropMeta meta, List<string> warnings, out bool hasLight)
        {
            hasLight = false;
            var model = LoadModel(name);
            if (model == null) { warnings.Add(name + ": 모델을 불러오지 못했어요"); return false; }
            // Main 슬롯이 없는 식물(풀·꽃)은 굽기 재질을 만들지 않는다
            Material main;
            if (UsesMain(model))
            {
                main = MainMaterial(name, meta, warnings);
                if (main == null) { warnings.Add(name + ": URP Lit 셰이더가 없어 재질을 만들지 못했어요"); return false; }
                if (FindTexture(KitFolder, name + "_albedo") == null)
                    warnings.Add(name + ": 색 텍스처(" + name + "_albedo.jpg/.png)가 없어요");
            }
            else main = FoliageMaterial();

            var scene = EditorSceneManager.NewPreviewScene();
            try
            {
                GameObject root = meta.IsDetail ? BuildDetailRoot(name, model, meta, main, scene, warnings)
                                                : BuildModelRoot(name, model, meta, main, scene, warnings, out hasLight);
                if (root == null) return false;
                bool ok;
                PrefabUtility.SaveAsPrefabAsset(root, PrefabPath(name), out ok);
                if (!ok) warnings.Add(name + ": 프리팹 저장에 실패했어요");
                return ok;
            }
            finally
            {
                EditorSceneManager.ClosePreviewScene(scene);
            }
        }

        static bool UsesMain(GameObject model)
        {
            foreach (var r in model.GetComponentsInChildren<Renderer>(true))
                foreach (var m in r.sharedMaterials)
                {
                    string n = m != null ? m.name : "";
                    if (!n.StartsWith("Glow") && !n.StartsWith("Foliage")) return true;
                }
            return false;
        }

        static MeshRenderer FindLod0Renderer(GameObject model, string name)
        {
            MeshRenderer first = null;
            foreach (var r in model.GetComponentsInChildren<MeshRenderer>(true))
            {
                if (first == null) first = r;
                if (r.name.EndsWith("_LOD0")) return r;
            }
            return first;
        }

        // 지형 풀: 지형이 프로토타입 뿌리의 MeshFilter·MeshRenderer 를 인스턴싱으로 그리므로 뿌리에 LOD0 메쉬 하나만 둔다
        static GameObject BuildDetailRoot(string name, GameObject model, PropMeta meta, Material main, UnityEngine.SceneManagement.Scene scene, List<string> warnings)
        {
            var src = FindLod0Renderer(model, name);
            var srcFilter = src != null ? src.GetComponent<MeshFilter>() : null;
            if (srcFilter == null || srcFilter.sharedMesh == null) { warnings.Add(name + ": 메쉬를 찾지 못했어요"); return null; }
            var go = new GameObject(name);
            UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(go, scene);
            go.AddComponent<MeshFilter>().sharedMesh = srcFilter.sharedMesh;
            var mr = go.AddComponent<MeshRenderer>();
            var mats = src.sharedMaterials;
            var foliage = FoliageMaterial();
            for (int i = 0; i < mats.Length; i++)
            {
                var pm = PickMaterial(mats[i] != null ? mats[i].name : "", main, warnings, name);
                mats[i] = pm != null && pm == foliage ? FoliageDetailMaterial() : pm;     // 지형 풀은 거리 축소가 켜진 재질
            }
            mr.sharedMaterials = mats;
            mr.shadowCastingMode = meta.shadows ? ShadowCastingMode.On : ShadowCastingMode.Off;
            mr.receiveShadows = true;
            mr.lightProbeUsage = LightProbeUsage.Off;
            mr.reflectionProbeUsage = ReflectionProbeUsage.Off;
            return go;
        }

        static GameObject BuildModelRoot(string name, GameObject model, PropMeta meta, Material main, UnityEngine.SceneManagement.Scene scene,
                                         List<string> warnings, out bool hasLight)
        {
            hasLight = false;
            var root = (GameObject)PrefabUtility.InstantiatePrefab(model, scene);
            root.name = name;
            root.transform.localPosition = Vector3.zero;
            root.transform.localRotation = Quaternion.identity;
            root.transform.localScale = Vector3.one;

            // 재질 교체 + 그림자
            var renderers = root.GetComponentsInChildren<Renderer>(true);
            foreach (var r in renderers)
            {
                var mats = r.sharedMaterials;
                for (int i = 0; i < mats.Length; i++) mats[i] = PickMaterial(mats[i] != null ? mats[i].name : "", main, warnings, name);
                r.sharedMaterials = mats;
                r.shadowCastingMode = meta.shadows ? ShadowCastingMode.On : ShadowCastingMode.Off;
                r.receiveShadows = true;
            }

            // LOD: 가져올 때 _LOD0, _LOD1 이름으로 자동 생긴 LODGroup 의 전환 높이를 크기에 맞게 다시 정한다
            var groups = LodRendererGroups(root, renderers);
            var lg = root.GetComponent<LODGroup>();
            if (lg == null) lg = root.AddComponent<LODGroup>();
            var bounds = RootBounds(root, groups[0]);
            float size = Mathf.Max(bounds.size.x, bounds.size.y, bounds.size.z, 0.1f);
            // 광원을 품은 소품(초·버섯)은 몸체 없이 땅만 빛나 보이는 일이 적도록 더 멀리(50 m)까지 둔다
            float[] heights = LodHeights(groups.Count, size, meta.cull, meta.hasLight && !meta.IsTree ? 50f : 30f);
            var lods = new LOD[groups.Count];
            for (int i = 0; i < lods.Length; i++) lods[i] = new LOD(heights[i], groups[i]);
            lg.SetLODs(lods);
            lg.fadeMode = LODFadeMode.CrossFade;
            lg.animateCrossFading = true;
            lg.RecalculateBounds();

            // 충돌
            AddCollider(root, meta, groups, bounds, warnings);

            // 발광 부품 자리의 점광원 (지형 나무는 지형이 그리므로 자식 광원이 생기지 않는다)
            if (meta.hasLight)
            {
                if (meta.IsTree) warnings.Add(name + ": 지형 나무(kind=tree)에는 광원을 넣을 수 없어 빼고 만들었어요");
                else
                {
                    var lgo = new GameObject("Glow Light");
                    lgo.transform.SetParent(root.transform, false);
                    lgo.transform.localPosition = PropMeta.BlenderToUnityLocal(meta.lightOffsetBlender);
                    var l = lgo.AddComponent<Light>();
                    l.type = LightType.Point;
                    l.color = meta.lightColor;
                    l.intensity = meta.lightIntensity;
                    l.range = meta.lightRange;
                    l.shadows = LightShadows.None;
                    if (meta.lightFar > 0f) lgo.AddComponent<LightCullDistance>().far = meta.lightFar;   // 등대 빛
                    lgo.AddComponent<SoulFlicker>();
                    hasLight = true;
                }
            }

            // 정적 플래그: 가림 컬링용. 정적 배칭은 쓰지 않는다 (소품 수천 개를 합치면 메모리가 커지고, SRP Batcher 로 충분)
            if (!meta.IsTree)
            {
                var flags = StaticEditorFlags.OccludeeStatic | StaticEditorFlags.ReflectionProbeStatic;
                if (meta.kind == "landmark" || size > 6f) flags |= StaticEditorFlags.OccluderStatic;
                foreach (var t in root.GetComponentsInChildren<Transform>(true))
                    if (t.GetComponent<Light>() == null) GameObjectUtility.SetStaticEditorFlags(t.gameObject, flags);
            }
            return root;
        }

        // LOD 별 렌더러 묶음 (가져온 LODGroup 이 있으면 그 순서, 없으면 이름의 _LODn, 그것도 없으면 전부 한 묶음)
        static List<Renderer[]> LodRendererGroups(GameObject root, Renderer[] renderers)
        {
            var groups = new List<Renderer[]>();
            var lg = root.GetComponent<LODGroup>();
            if (lg != null)
            {
                foreach (var lod in lg.GetLODs())
                {
                    var list = new List<Renderer>();
                    if (lod.renderers != null) foreach (var r in lod.renderers) if (r != null) list.Add(r);
                    if (list.Count > 0) groups.Add(list.ToArray());
                }
                if (groups.Count > 0) return groups;
            }
            var byLevel = new SortedDictionary<int, List<Renderer>>();
            foreach (var r in renderers)
            {
                int idx = r.name.LastIndexOf("_LOD");
                int level;
                if (idx < 0 || !int.TryParse(r.name.Substring(idx + 4), out level)) level = 0;
                if (!byLevel.ContainsKey(level)) byLevel[level] = new List<Renderer>();
                byLevel[level].Add(r);
            }
            foreach (var kv in byLevel) groups.Add(kv.Value.ToArray());
            if (groups.Count == 0) groups.Add(renderers);
            return groups;
        }

        // 뿌리 공간의 경계 상자 (뿌리는 원점·회전 없음)
        static Bounds RootBounds(GameObject root, Renderer[] lod0)
        {
            bool any = false;
            var b = new Bounds();
            foreach (var r in lod0)
            {
                var mf = r.GetComponent<MeshFilter>();
                if (mf == null || mf.sharedMesh == null) continue;
                var mb = mf.sharedMesh.bounds;
                Matrix4x4 m = root.transform.worldToLocalMatrix * r.transform.localToWorldMatrix;
                for (int c = 0; c < 8; c++)
                {
                    var p = m.MultiplyPoint3x4(mb.center + Vector3.Scale(mb.extents, new Vector3((c & 1) == 0 ? -1 : 1, (c & 2) == 0 ? -1 : 1, (c & 4) == 0 ? -1 : 1)));
                    if (!any) { b = new Bounds(p, Vector3.zero); any = true; }
                    else b.Encapsulate(p);
                }
            }
            if (!any) b = new Bounds(new Vector3(0f, 0.5f, 0f), Vector3.one);
            return b;
        }

        // LOD 전환 화면 높이. 거리(m)로 정한 뒤 화면 높이로 바꾼다 (시야각 55도: 화면 높이 ≈ 크기 / (1.04 × 거리))
        // minCullDistance: META cull 이 커도 이 거리(m, lodBias 1 기준) 안에서는 사라지지 않게 한다.
        // 해골·버섯처럼 작은 소품이 카메라 거리(5~9 m) 안에서 사라지거나, 광원만 남고 몸체가 먼저 사라지는 것을 막는다
        public static float[] LodHeights(int n, float size, float cull, float minCullDistance = 30f)
        {
            cull = Mathf.Clamp(cull, 0f, 0.5f);
            if (minCullDistance > 0f) cull = Mathf.Min(cull, size / (1.04f * minCullDistance));
            var h = new float[n];
            System.Func<float, float> H = d => size / (1.04f * Mathf.Max(d, 1f));
            if (n == 1) { h[0] = cull; return h; }
            float d0 = Mathf.Clamp(size * 8f, 15f, 90f);
            float d1 = Mathf.Clamp(size * 25f, 45f, 300f);
            h[n - 1] = cull;
            if (n == 2) h[0] = Mathf.Max(H(d0), cull * 1.5f + 0.002f);
            else
            {
                h[1] = Mathf.Max(H(d1), cull * 1.3f + 0.001f);
                h[0] = Mathf.Max(H(d0), h[1] * 1.3f + 0.002f);
                // LOD 가 넷 이상이면 둘째와 마지막 사이를 고르게 나눈다
                for (int i = 2; i < n - 1; i++) h[i] = Mathf.Lerp(h[1], cull, (i - 1f) / (n - 2f)) + 0.0005f;
            }
            for (int i = 0; i < n; i++) h[i] = Mathf.Min(h[i], 0.95f - i * 0.01f);
            return h;
        }

        static void AddCollider(GameObject root, PropMeta meta, List<Renderer[]> groups, Bounds b, List<string> warnings)
        {
            string kind = meta.collider;
            if (kind == "none") return;
            // 지형 나무(kind = tree)는 지형 충돌이 프로토타입 뿌리의 캡슐 충돌을 쓴다
            if (meta.IsTree && kind != "capsule")
            {
                warnings.Add(meta.name + ": 지형 나무는 캡슐 충돌로 만들었어요 (META collider = " + kind + ")");
                kind = "capsule";
            }
            if (kind == "mesh")
            {
                // 가까이서 부딪히는 용도라 LOD1 (없으면 LOD0) 메쉬를 쓴다 (가볍게)
                var lod = groups[Mathf.Min(1, groups.Count - 1)];
                foreach (var r in lod)
                {
                    var mf = r.GetComponent<MeshFilter>();
                    if (mf == null || mf.sharedMesh == null) continue;
                    var mc = r.gameObject.AddComponent<MeshCollider>();
                    mc.sharedMesh = mf.sharedMesh;
                    return;
                }
                kind = "box";
            }
            if (kind == "box")
            {
                var bc = root.AddComponent<BoxCollider>();
                bc.center = b.center;
                bc.size = b.size;
                return;
            }
            if (kind == "capsule")
            {
                var cc = root.AddComponent<CapsuleCollider>();
                cc.direction = 1;
                bool fromBounds = meta.HasTag("rock") || meta.HasTag("cliff") || meta.HasTag("ruin");
                float radius = fromBounds ? Mathf.Min(b.size.x, b.size.z) * 0.45f : TrunkRadius(groups[0], root, b);
                cc.radius = Mathf.Max(0.1f, radius);
                cc.height = Mathf.Max(b.size.y, cc.radius * 2f);
                // 줄기 반지름(TrunkRadius)은 원점 축에서 쟀으므로 중심도 원점 축에 둔다 (등불 팔처럼 한쪽으로 뻗은 부품에 끌려가지 않게).
                // 경계 상자로 반지름을 정한 바위·폐허만 경계 상자 중심을 쓴다. 지형 나무는 늘 원점 축
                bool onAxis = meta.IsTree || !fromBounds;
                cc.center = new Vector3(onAxis ? 0f : b.center.x, b.min.y + cc.height * 0.5f, onAxis ? 0f : b.center.z);
                return;
            }
            warnings.Add(meta.name + ": 알 수 없는 collider '" + kind + "' → 충돌 없이 만들었어요");
        }

        // 나무 줄기 반지름: 땅 위 0.4~1.8 m 높이의 정점이 원점 축에서 떨어진 거리 (70번째 백분위).
        // 키가 2 m 보다 작은 소품(그루터기 등)은 0.4~1.8 m 띠에 윗면 정점이 섞여 반지름이 작아지므로 높이의 20~60% 띠에서 잰다
        static float TrunkRadius(Renderer[] lod0, GameObject root, Bounds b)
        {
            float fallback = Mathf.Clamp(Mathf.Min(b.size.x, b.size.z) * 0.12f, 0.2f, 1.0f);
            float bandLo = 0.4f, bandHi = 1.8f;
            if (b.size.y < 2f) { bandLo = b.size.y * 0.2f; bandHi = b.size.y * 0.6f; }
            var dists = new List<float>();
            foreach (var r in lod0)
            {
                var mf = r.GetComponent<MeshFilter>();
                if (mf == null || mf.sharedMesh == null) continue;
                Vector3[] verts = mf.sharedMesh.vertices;     // 에디터에서는 읽기 가능 설정과 상관없이 읽힌다 (못 읽으면 빈 배열)
                Matrix4x4 m = root.transform.worldToLocalMatrix * r.transform.localToWorldMatrix;
                for (int i = 0; i < verts.Length; i++)
                {
                    var p = m.MultiplyPoint3x4(verts[i]);
                    float y = p.y - b.min.y;
                    if (y < bandLo || y > bandHi) continue;
                    dists.Add(new Vector2(p.x, p.z).magnitude);
                }
            }
            if (dists.Count < 8) return fallback;
            dists.Sort();
            return Mathf.Clamp(dists[(int)(dists.Count * 0.7f)], 0.12f, Mathf.Max(0.2f, Mathf.Min(b.size.x, b.size.z) * 0.4f));
        }
    }
}
