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
        public Vector3 sizeBlender;
        public bool fromManifest;

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
            return path.StartsWith(KitFolder + "/") || path.StartsWith(WorldFolder + "/");
        }

        // 텍스처 가져오기 설정. 바뀐 것이 있으면 true
        public static bool ConfigureTexture(TextureImporter ti, string path)
        {
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
                    object lo;
                    if (meta.TryGetValue("light", out lo) && lo is Dictionary<string, object>)
                    {
                        var light = (Dictionary<string, object>)lo;
                        m.hasLight = true;
                        m.lightOffsetBlender = ctx.Vec3(light, "offset", where + ".light", Vector3.zero, false);
                        m.lightColor = ctx.Col(light, "color", where + ".light", m.lightColor, false);
                        m.lightIntensity = (float)ctx.Num(light, "intensity", where + ".light", m.lightIntensity, false);
                        m.lightRange = (float)ctx.Num(light, "range", where + ".light", m.lightRange, false);
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

        // 굽기 텍스처 재질 (URP Lit + 알베도 + 노멀). 이미 있으면 직접 조정한 값은 두고 텍스처만 새 것으로 바꾼다
        public static Material MainMaterial(string name)
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
            return m;
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
                             "\n가져오기 설정을 고친 파일: 텍스처 " + counts.textures + ", 모델 " + counts.models +
                             "\n걸린 시간 " + counts.seconds.ToString("0.0") + "초" + (warnings.Count > 0 ? ", 경고 " + warnings.Count + "개" : "");
            Debug.Log(summary);
            if (warnings.Count > 0) Debug.LogWarning("[Necro] 소품 프리팹 경고\n" + string.Join("\n", warnings.ToArray()));
        }

        public struct BuildCounts { public int prefabs, props, trees, details, lights, textures, models; public float seconds; }

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
                string full = NecroEditorUtil.FullPath(KitFolder);
                var reimport = new List<AssetImporter>();
                foreach (var f in Directory.GetFiles(full))
                {
                    string ext = Path.GetExtension(f).ToLowerInvariant();
                    string assetPath = KitFolder + "/" + Path.GetFileName(f);
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
                main = MainMaterial(name);
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
            for (int i = 0; i < mats.Length; i++) mats[i] = PickMaterial(mats[i] != null ? mats[i].name : "", main, warnings, name);
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
