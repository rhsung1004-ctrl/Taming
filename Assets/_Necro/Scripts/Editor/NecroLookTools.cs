using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Necro.EditorTools
{
    // 룩 확정 단계 도구: 애니풍 다크 판타지 분위기(밤하늘·달빛·안개·후처리)와 툰 셰이더를 원클릭으로 적용한다.
    // 묘지 테스트 장면의 지형·묘비는 분위기 확인용 임시 도형이다. 실제 배경 모델이 생기면 교체한다.
    public static class NecroLookTools
    {
        public const string ToonShaderName = "Necro/Toon";
        public const string PlaceholderName = "주인공 임시 모델";
        const string SettingsFolder = "Assets/_Necro/Settings";
        const string LookMatFolder = "Assets/_Necro/Art/Materials/Look";
        const string ToonMatFolder = "Assets/_Necro/Art/Materials/Toon";
        const string SceneFolder = "Assets/_Necro/Scenes";
        const string ScenePath = SceneFolder + "/Look_Graveyard.unity";
        const string ProfilePath = SettingsFolder + "/DarkFantasyProfile.asset";
        // Blender로 만든 묘지 소품 (모델 .fbx + 색 _albedo.jpg(이전 버전 .png) + 굴곡 _normal.png).
        // '월드 → 0. 소품 가져오기 설정 + 프리팹 만들기'로 만든 프리팹이 있으면 프리팹을 쓴다
        const string KitFolder = NecroProps.KitFolder;
        const string PropMatFolder = NecroProps.MatFolder;

        static readonly Color Horizon = new Color(0.16f, 0.12f, 0.27f);
        static readonly Color Soul = new Color(0.72f, 0.45f, 1f);

        // ───────────── 공통 도우미 ─────────────
        static void EnsureFolder(string path)
        {
            if (AssetDatabase.IsValidFolder(path)) return;
            string parent = Path.GetDirectoryName(path).Replace('\\', '/');
            EnsureFolder(parent);
            AssetDatabase.CreateFolder(parent, Path.GetFileName(path));
        }

        static Shader FindShader(string name)
        {
            var s = Shader.Find(name);
            if (s == null)
                EditorUtility.DisplayDialog("셰이더를 찾을 수 없어요",
                    "'" + name + "' 셰이더가 없습니다.\nConsole 창에 빨간 셰이더 에러가 있는지 확인하고, 있으면 그 내용을 Claude에게 보내 주세요.", "확인");
            return s;
        }

        // 이미 있으면 그대로 쓴다 (직접 조정한 값을 덮어쓰지 않기 위해)
        static Material LoadOrCreate(string folder, string name, string shaderName, System.Action<Material> setup)
        {
            EnsureFolder(folder);
            string path = folder + "/" + name + ".mat";
            var m = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (m != null) return m;
            var sh = FindShader(shaderName);
            if (sh == null) return null;
            m = new Material(sh);
            m.name = name;
            if (setup != null) setup(m);
            AssetDatabase.CreateAsset(m, path);
            return m;
        }

        static Material Lit(string name, Color c, float smoothness = 0.1f)
        {
            return LoadOrCreate(LookMatFolder, name, "Universal Render Pipeline/Lit", m =>
            {
                m.SetColor("_BaseColor", c);
                m.SetFloat("_Smoothness", smoothness);
            });
        }

        static Material Toon(string name, Color c, System.Action<Material> extra = null)
        {
            return LoadOrCreate(LookMatFolder, name, ToonShaderName, m =>
            {
                m.SetColor("_BaseColor", c);
                m.enableInstancing = true;
                if (extra != null) extra(m);
            });
        }

        static GameObject Prim(PrimitiveType type, string name, Transform parent, Vector3 pos, Vector3 scale, Material mat,
                               Vector3 euler = default(Vector3), bool collider = true)
        {
            var g = GameObject.CreatePrimitive(type);
            g.name = name;
            if (parent != null) g.transform.SetParent(parent, false);
            g.transform.localPosition = pos;
            g.transform.localEulerAngles = euler;
            g.transform.localScale = scale;
            if (mat != null) g.GetComponent<Renderer>().sharedMaterial = mat;
            if (!collider) Object.DestroyImmediate(g.GetComponent<Collider>());
            return g;
        }

        static Light PointLight(string name, Transform parent, Vector3 pos, Color c, float range, float intensity, bool flicker)
        {
            var g = new GameObject(name);
            if (parent != null) g.transform.SetParent(parent, false);
            g.transform.localPosition = pos;
            var l = g.AddComponent<Light>();
            l.type = LightType.Point;
            l.color = c;
            l.range = range;
            l.intensity = intensity;
            l.shadows = LightShadows.None;
            if (flicker) g.AddComponent<SoulFlicker>();
            return l;
        }

        // ───────────── 분위기: 밤하늘·달빛·안개·후처리 ─────────────
        [MenuItem("Tools/Necro/룩/현재 씬에 다크 판타지 분위기 적용", priority = 12)]
        public static void ApplyLookMenu()
        {
            ApplyLook();
            EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
            Debug.Log("[Necro] 다크 판타지 분위기 적용 완료. 후처리 값은 " + ProfilePath + ", 하늘은 " + LookMatFolder + "/NecroSky 에서 조정하세요.");
        }

        public static Light ApplyLook()
        {
            EnsureFolder(SettingsFolder);

            // 후처리
            var profile = AssetDatabase.LoadAssetAtPath<VolumeProfile>(ProfilePath);
            if (profile == null)
            {
                profile = ScriptableObject.CreateInstance<VolumeProfile>();
                AssetDatabase.CreateAsset(profile, ProfilePath);

                var bloom = profile.Add<Bloom>(true);              // 영혼 불꽃·등불이 번지는 빛
                bloom.threshold.Override(0.95f);
                bloom.intensity.Override(1.1f);
                bloom.scatter.Override(0.72f);
                bloom.tint.Override(new Color(0.85f, 0.78f, 1f));
                AssetDatabase.AddObjectToAsset(bloom, profile);

                var tone = profile.Add<Tonemapping>(true);          // Neutral: 애니풍 색이 탁해지지 않는다
                tone.mode.Override(TonemappingMode.Neutral);
                AssetDatabase.AddObjectToAsset(tone, profile);

                var color = profile.Add<ColorAdjustments>(true);
                color.postExposure.Override(0.25f);
                color.contrast.Override(14f);
                color.saturation.Override(10f);
                AssetDatabase.AddObjectToAsset(color, profile);

                var split = profile.Add<SplitToning>(true);         // 어두운 곳은 보라, 밝은 곳은 차가운 달빛
                split.shadows.Override(new Color(0.42f, 0.34f, 0.62f));
                split.highlights.Override(new Color(0.58f, 0.62f, 0.72f));
                split.balance.Override(-10f);
                AssetDatabase.AddObjectToAsset(split, profile);

                var vig = profile.Add<Vignette>(true);
                vig.intensity.Override(0.3f);
                vig.smoothness.Override(0.45f);
                vig.color.Override(new Color(0.04f, 0.02f, 0.08f));
                AssetDatabase.AddObjectToAsset(vig, profile);

                EditorUtility.SetDirty(profile);
                AssetDatabase.SaveAssets();
            }

            var volGo = GameObject.Find("Necro Look Volume");
            if (volGo == null) volGo = new GameObject("Necro Look Volume");
            var vol = volGo.GetComponent<Volume>();
            if (vol == null) vol = volGo.AddComponent<Volume>();
            vol.isGlobal = true;
            vol.priority = 10f;
            vol.sharedProfile = profile;

            var cam = Camera.main;
            if (cam != null)
            {
                var data = cam.GetComponent<UniversalAdditionalCameraData>();
                if (data == null) data = cam.gameObject.AddComponent<UniversalAdditionalCameraData>();
                data.renderPostProcessing = true;
                data.antialiasing = AntialiasingMode.SubpixelMorphologicalAntiAliasing;   // 외곽선 계단을 줄인다
                cam.farClipPlane = 600f;
                cam.fieldOfView = 55f;
                cam.allowHDR = true;
            }

            // 달빛 (씬의 방향광 하나를 달로 쓴다)
            Light moon = null;
#if UNITY_2023_1_OR_NEWER
            var lights = Object.FindObjectsByType<Light>(FindObjectsSortMode.None);
#else
            var lights = Object.FindObjectsOfType<Light>();
#endif
            foreach (var l in lights) if (l.type == LightType.Directional) moon = l;
            if (moon == null)
            {
                moon = new GameObject("Moon Light").AddComponent<Light>();
                moon.type = LightType.Directional;
            }
            moon.transform.rotation = Quaternion.Euler(38f, -150f, 0f);
            moon.color = new Color(0.62f, 0.7f, 1f);
            moon.intensity = 1.25f;
            moon.shadows = LightShadows.Soft;
            moon.shadowStrength = 0.85f;
            RenderSettings.sun = moon;

            // 하늘
            var sky = LoadOrCreate(LookMatFolder, "NecroSky", "Necro/Sky", m => m.SetColor("_HorizonColor", Horizon));
            if (sky != null)
            {
                Vector3 toMoon = -moon.transform.forward;
                sky.SetVector("_MoonDir", new Vector4(toMoon.x, toMoon.y, toMoon.z, 0f));
                EditorUtility.SetDirty(sky);
                RenderSettings.skybox = sky;
            }

            // 주변광: 그늘도 보랏빛으로 살아 있게
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.2f, 0.2f, 0.36f);
            RenderSettings.ambientEquatorColor = new Color(0.17f, 0.14f, 0.27f);
            RenderSettings.ambientGroundColor = new Color(0.07f, 0.06f, 0.11f);
            RenderSettings.reflectionIntensity = 0.3f;

            // 안개: 지평선 색과 같게 해서 먼 곳이 하늘에 녹아들게
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.ExponentialSquared;
            RenderSettings.fogColor = Horizon;
            RenderSettings.fogDensity = 0.016f;

            // 분위기 프리셋 (플레이 중 F3으로 넘겨 가며 비교)
            var cycler = volGo.GetComponent<LookPresetCycler>();
            if (cycler == null) cycler = volGo.AddComponent<LookPresetCycler>();
            cycler.moon = moon;
            cycler.volume = vol;
            if (cycler.presets == null || cycler.presets.Length == 0) cycler.presets = DefaultPresets();
            EditorUtility.SetDirty(cycler);
            return moon;
        }

        static LookPreset[] DefaultPresets()
        {
            return new[]
            {
                new LookPreset { name = "차가운 달빛 (기본)" },
                new LookPreset
                {
                    name = "핏빛 황혼",
                    moonColor = new Color(1f, 0.5f, 0.42f), moonIntensity = 1.35f, moonAngles = new Vector2(14f, -160f),
                    ambientSky = new Color(0.3f, 0.14f, 0.22f), ambientEquator = new Color(0.26f, 0.1f, 0.14f), ambientGround = new Color(0.1f, 0.04f, 0.06f),
                    fogColor = new Color(0.36f, 0.1f, 0.13f), fogDensity = 0.018f, skyTop = new Color(0.07f, 0.02f, 0.08f),
                    moonDisc = new Color(2.6f, 0.7f, 0.5f), starBrightness = 0.6f,
                    exposure = 0.2f, saturation = 14f, shadowTint = new Color(0.55f, 0.28f, 0.42f)
                },
                new LookPreset
                {
                    name = "영혼 안개",
                    moonColor = new Color(0.5f, 0.85f, 0.85f), moonIntensity = 0.9f, moonAngles = new Vector2(55f, -120f),
                    ambientSky = new Color(0.14f, 0.3f, 0.32f), ambientEquator = new Color(0.12f, 0.22f, 0.26f), ambientGround = new Color(0.05f, 0.09f, 0.1f),
                    fogColor = new Color(0.12f, 0.24f, 0.27f), fogDensity = 0.034f, skyTop = new Color(0.01f, 0.05f, 0.07f),
                    moonDisc = new Color(1.2f, 2.2f, 2.0f), starBrightness = 0.5f,
                    exposure = 0.35f, saturation = 4f, shadowTint = new Color(0.3f, 0.5f, 0.55f)
                },
                new LookPreset
                {
                    name = "잿빛 새벽",
                    moonColor = new Color(0.8f, 0.82f, 0.9f), moonIntensity = 1.6f, moonAngles = new Vector2(24f, -140f),
                    ambientSky = new Color(0.34f, 0.36f, 0.46f), ambientEquator = new Color(0.28f, 0.28f, 0.36f), ambientGround = new Color(0.12f, 0.11f, 0.14f),
                    fogColor = new Color(0.34f, 0.35f, 0.45f), fogDensity = 0.022f, skyTop = new Color(0.1f, 0.11f, 0.2f),
                    moonDisc = new Color(1.3f, 1.3f, 1.5f), starBrightness = 0.25f,
                    exposure = 0.1f, saturation = -8f, shadowTint = new Color(0.4f, 0.4f, 0.55f)
                },
            };
        }

        // ───────────── 묘지 룩 테스트 장면 ─────────────
        [MenuItem("Tools/Necro/룩/묘지 룩 테스트 장면 만들기", priority = 11)]
        public static void BuildLookScene()
        {
            if (FindShader(ToonShaderName) == null) return;
            if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
            if (File.Exists(ScenePath))
            {
                int choice = EditorUtility.DisplayDialogComplex("묘지 룩 테스트 장면",
                    "이미 만든 장면이 있어요. 새로 만들면 그 장면에서 직접 배치·수정한 것이 사라집니다.\n(머티리얼과 후처리 설정은 그대로 남습니다)",
                    "기존 장면 열기", "취소", "새로 만들기");
                if (choice == 1) return;
                if (choice == 0) { EditorSceneManager.OpenScene(ScenePath); return; }
            }

            EnsureFolder(SceneFolder);
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            var camGo = new GameObject("Main Camera");
            camGo.tag = "MainCamera";
            camGo.AddComponent<Camera>();
            camGo.AddComponent<AudioListener>();
            camGo.transform.position = new Vector3(0f, 2.2f, -17f);

            ApplyLook();

            var rnd = new System.Random(7);
            bool kit = HasKit();
            var env = new GameObject(kit ? "Environment" : "Environment (임시 도형)").transform;
            if (kit) BuildKitEnvironment(env, rnd);
            else BuildPrimitiveEnvironment(env, rnd);

            BuildParticles(env);
            BuildDummies(env);

            // 걸어 다닐 임시 주인공 (VRoid 모델이 생기면 'Tools → Necro → 2. 선택한 모델로 플레이어 만들기'로 교체)
            var hero = BuildPlaceholderHero();
            hero.transform.position = new Vector3(0f, 0f, -12f);
            NecroSetupTools.BuildPlayer(hero);

            EditorSceneManager.SaveScene(scene, ScenePath);
            AssetDatabase.SaveAssets();
            if (!kit)
                Debug.LogWarning("[Necro] 묘지 소품 모델(" + KitFolder + ")을 찾지 못해 임시 도형으로 만들었어요. git lfs pull 을 실행한 뒤 다시 만들어 보세요.");
            Debug.Log("[Necro] 묘지 룩 테스트 장면을 만들었어요: " + ScenePath + "\nPlay를 누르고 걸어 다니며 분위기를 확인하세요. 제단 앞의 세 인형은 툰 셰이더 비교용입니다 (적 / 지배된 망자 / 금속 갑옷).");
        }

        // 걸어 다닐 임시 주인공 인형 (월드 도구도 쓴다)
        public static GameObject BuildPlaceholderHero()
        {
            return BuildMannequin(PlaceholderName,
                Toon("Hero_Robe", new Color(0.24f, 0.16f, 0.4f)),
                Toon("Hero_Skin", new Color(0.98f, 0.88f, 0.84f), m => m.SetColor("_ShadeColor", new Color(0.78f, 0.6f, 0.72f))),
                Toon("Hero_Hair", new Color(0.8f, 0.74f, 0.95f), m => { m.SetFloat("_SpecStrength", 0.6f); m.SetFloat("_SpecSize", 0.12f); }));
        }

        // ───────────── 묘지 소품으로 장면 짓기 ─────────────
        // 프리팹이 있거나, 모델과 색 텍스처(jpg 또는 png)가 있으면 실제 소품으로 짓는다
        static bool HasKit()
        {
            if (NecroProps.LoadPrefab("grave_slab_a") != null) return true;
            return NecroProps.LoadModel("grave_slab_a") != null && NecroProps.FindTexture(KitFolder, "grave_slab_a_albedo") != null;
        }

        static Texture2D NormalMap(string path)
        {
            var imp = AssetImporter.GetAtPath(path) as TextureImporter;
            if (imp != null && imp.textureType != TextureImporterType.NormalMap)
            {
                imp.textureType = TextureImporterType.NormalMap;
                imp.SaveAndReimport();
            }
            return AssetDatabase.LoadAssetAtPath<Texture2D>(path);
        }

        static Material TexturedLit(string name, string texBase, float tiling)
        {
            return LoadOrCreate(PropMatFolder, name, "Universal Render Pipeline/Lit", m =>
            {
                var albedo = NecroProps.FindTexture(Path.GetDirectoryName(texBase).Replace('\\', '/'), Path.GetFileName(texBase) + "_albedo");
                var normal = NormalMap(texBase + "_normal.png");
                if (albedo != null) m.SetTexture("_BaseMap", albedo);
                if (normal != null)
                {
                    m.SetTexture("_BumpMap", normal);
                    m.EnableKeyword("_NORMALMAP");
                }
                m.SetColor("_BaseColor", Color.white);
                m.SetFloat("_Smoothness", 0.12f);
                if (tiling != 1f) m.SetTextureScale("_BaseMap", new Vector2(tiling, tiling));
            });
        }

        // 소품 하나 놓기. 좌표는 위에서 본 배치도 기준 (x: 오른쪽, y: 안쪽), rz: 반시계 회전(도).
        // Blender에서 만든 방향 그대로 놓이도록 180도 돌려서 둔다 (SPEC: Unity Y 회전 = 180 − rz).
        // 프리팹(재질·충돌·LOD·광원이 이미 들어 있다)이 있으면 프리팹, 없으면 모델을 놓고 재질·충돌을 붙인다.
        static GameObject Place(string name, Transform parent, float x, float y, float rz = 0f, float scale = 1f, float tiltX = 0f, float tiltZ = 0f, float sink = 0f)
        {
            var prefab = NecroProps.LoadPrefab(name);
            var src = prefab != null ? prefab : NecroProps.LoadModel(name);
            if (src == null) return null;
            var go = (GameObject)PrefabUtility.InstantiatePrefab(src);
            go.name = name;
            go.transform.SetParent(parent, false);
            go.transform.localPosition = new Vector3(x, -sink, y);
            go.transform.localRotation = Quaternion.Euler(tiltX, 180f - rz, tiltZ);
            go.transform.localScale = Vector3.one * scale;
            if (prefab != null) return go;
            var main = NecroProps.MainMaterial(name);
            var renderers = go.GetComponentsInChildren<Renderer>(true);
            // 충돌은 LOD 하나에만 단다 (프리팹의 메쉬 충돌과 같게 LOD1, 없으면 LOD0). LOD 이름이 없는 모델만 렌더러마다 단다
            Renderer colliderOwner = null;
            foreach (var r in renderers)
            {
                if (r.name.EndsWith("_LOD1")) { colliderOwner = r; break; }
                if (colliderOwner == null && r.name.EndsWith("_LOD0")) colliderOwner = r;
            }
            foreach (var r in renderers)
            {
                var mats = r.sharedMaterials;
                for (int i = 0; i < mats.Length; i++)
                    mats[i] = NecroProps.PickMaterial(mats[i] != null ? mats[i].name : "", main, null, name);
                r.sharedMaterials = mats;
                if (colliderOwner != null && r != colliderOwner) continue;
                var mf = r.GetComponent<MeshFilter>();
                if (mf != null && mf.sharedMesh != null && r.GetComponent<Collider>() == null)
                    r.gameObject.AddComponent<MeshCollider>().sharedMesh = mf.sharedMesh;
            }
            return go;
        }

        static float Rand(System.Random rnd, float a, float b) { return a + (float)rnd.NextDouble() * (b - a); }

        static bool HasOwnLight(GameObject go) { return go != null && go.GetComponentInChildren<Light>(true) != null; }

        static void BuildKitEnvironment(Transform env, System.Random rnd)
        {
            // 땅: 이어 붙는 흙바닥 텍스처 (4m마다 반복). 등불 빛이 타일마다 따로 닿도록 20m 타일로 나눈다
            Material ground = TexturedLit("Ground", KitFolder + "/ground", 5f);
            var groundRoot = new GameObject("Ground").transform;
            groundRoot.SetParent(env, false);
            for (int x = -3; x < 3; x++)
                for (int z = -3; z < 3; z++)
                    Prim(PrimitiveType.Plane, "Tile", groundRoot, new Vector3(x * 20f + 10f, 0f, z * 20f + 10f), new Vector3(2f, 1f, 2f), ground);

            // 봉인의 제단과 둘러선 기둥
            var center = new GameObject("Altar Area").transform;
            center.SetParent(env, false);
            var altar = Place("altar", center, 0f, 6f);
            if (!HasOwnLight(altar))
            {
                var altarLight = PointLight("Soul Light", center, new Vector3(0f, 2.7f, 6f), Soul, 18f, 30f, true);
                altarLight.GetComponent<SoulFlicker>().amount = 0.3f;
            }
            string[] pillars = { "pillar_a", "pillar_b", "pillar_a", "pillar_a", "pillar_b" };
            for (int i = 0; i < pillars.Length; i++)
            {
                float a = i * Mathf.PI * 2f / 5f + 0.3f;
                Place(pillars[i], center, Mathf.Cos(a) * 4.3f, 6f + Mathf.Sin(a) * 4.3f, (a + 1f) * Mathf.Rad2Deg);
            }

            // 납골당과 입구의 무너진 아치
            var crypt = Place("crypt", env, 0f, 25f);
            if (!HasOwnLight(crypt))      // 프리팹에 META 광원이 들어 있으면 입구 광원을 또 놓지 않는다
                PointLight("Crypt Light", env, new Vector3(0f, 3f, 21.5f), new Color(0.45f, 1f, 0.6f), 14f, 16f, true);
            Place("arch_ruin", env, 0f, -8.5f);

            // 영혼 등불
            var lanterns = new GameObject("Soul Lanterns").transform;
            lanterns.SetParent(env, false);
            float[,] spots = { { -3.2f, -6f, 11f }, { 3.2f, -1f, 166f }, { -3.4f, 2f, 23f }, { -13f, 10f, 57f }, { 12f, 13f, 206f }, { -9f, -4f, 17f }, { 15f, -2f, 143f } };
            for (int i = 0; i < spots.GetLength(0); i++)
            {
                float x = spots[i, 0], y = spots[i, 1], rz = spots[i, 2];
                var lantern = Place("lantern", lanterns, x, y, rz);
                if (HasOwnLight(lantern)) continue;      // 프리팹에 META 광원이 이미 들어 있다
                float r = rz * Mathf.Deg2Rad;
                PointLight("Lantern Light", lanterns, new Vector3(x + Mathf.Cos(r) * 0.5f, 2.28f, y + Mathf.Sin(r) * 0.5f), Soul, 9f, 9f, true);
            }

            // 길 양옆의 철 울타리
            var fences = new GameObject("Fences").transform;
            fences.SetParent(env, false);
            for (int sx = -1; sx <= 1; sx += 2)
            {
                for (int i = 0; i < 5; i++)
                    Place("fence", fences, sx * 7.5f, -9f + i * 3.4f, 90f + Rand(rnd, -3f, 3f), 1f, Rand(rnd, -3f, 3f));
                Place("fence", fences, sx * 4.3f, -9.6f, Rand(rnd, -4f, 4f));
            }

            // 묘비
            var graves = new GameObject("Graves").transform;
            graves.SetParent(env, false);
            string[] kinds = { "grave_slab_a", "grave_slab_b", "grave_cross", "grave_obelisk" };
            int placed = 0;
            for (int guard = 0; guard < 600 && placed < 64; guard++)
            {
                float x = Rand(rnd, -32f, 32f), y = Rand(rnd, -9f, 23f);
                if (Mathf.Abs(x) < 2.6f && y < 2f) continue;                          // 돌길
                if (x * x + (y - 6f) * (y - 6f) < 36f) continue;                     // 제단
                if (Mathf.Abs(x) < 8f && y > 17f) continue;                          // 납골당
                if (Mathf.Abs(Mathf.Abs(x) - 7.5f) < 1.2f && y < 8f) continue;       // 울타리
                Place(kinds[rnd.Next(kinds.Length)], graves, x, y, rnd.Next(2) * 180f + Rand(rnd, -18f, 18f), Rand(rnd, 0.9f, 1.2f),
                      Rand(rnd, -7f, 7f), Rand(rnd, -7f, 7f), Rand(rnd, 0f, 0.06f));
                placed++;
            }

            // 죽은 나무
            var trees = new GameObject("Dead Trees").transform;
            trees.SetParent(env, false);
            for (int i = 0; i < 16; i++)
            {
                float a = Rand(rnd, 0f, Mathf.PI * 2f), d = Rand(rnd, 12f, 34f);
                float x = Mathf.Cos(a) * d, y = 6f + Mathf.Sin(a) * d;
                if (Mathf.Abs(x) < 9f && y > 15f) continue;
                if (Mathf.Abs(x) < 5f && y < 0f) continue;
                Place(rnd.Next(2) == 0 ? "dead_tree_a" : "dead_tree_b", trees, x, y, Rand(rnd, 0f, 360f), Rand(rnd, 0.9f, 1.5f));
            }
            Place("dead_tree_a", trees, -6.2f, -3.5f, 69f, 1.25f);
            Place("dead_tree_b", trees, 8.5f, 3f, 229f, 1.3f);

            // 바위
            var rocks = new GameObject("Rocks").transform;
            rocks.SetParent(env, false);
            string[] rockKinds = { "rock_a", "rock_b", "rock_c", "rock_c" };
            for (int i = 0; i < 28; i++)
            {
                float x = Rand(rnd, -28f, 28f), y = Rand(rnd, -10f, 24f);
                if (Mathf.Abs(x) < 2.5f && y < 3f) continue;
                if (x * x + (y - 6f) * (y - 6f) < 25f) continue;
                Place(rockKinds[rnd.Next(rockKinds.Length)], rocks, x, y, Rand(rnd, 0f, 360f), Rand(rnd, 0.5f, 1.1f), 0f, 0f, Rand(rnd, 0f, 0.15f));
            }
        }

        // 소품 모델이 없을 때 쓰는 임시 도형 장면
        static void BuildPrimitiveEnvironment(Transform env, System.Random rnd)
        {

            Material ground = Lit("Ground", new Color(0.085f, 0.085f, 0.105f));
            Material stone = Lit("Stone", new Color(0.3f, 0.3f, 0.36f), 0.2f);
            Material stoneDark = Lit("StoneDark", new Color(0.15f, 0.14f, 0.19f), 0.15f);
            Material bark = Lit("Bark", new Color(0.1f, 0.08f, 0.1f));
            Material soulGlow = Toon("SoulGlow", Soul, m =>
            {
                m.SetColor("_EmissionColor", new Color(2.6f, 1.4f, 4.6f));
                m.SetFloat("_OutlineWidth", 0f);
            });

            // 땅: 등불 빛이 타일마다 따로 닿도록 20m 타일로 나눈다
            var groundRoot = new GameObject("Ground").transform;
            groundRoot.SetParent(env, false);
            for (int x = -3; x < 3; x++)
                for (int z = -3; z < 3; z++)
                    Prim(PrimitiveType.Plane, "Tile", groundRoot, new Vector3(x * 20f + 10f, 0f, z * 20f + 10f), new Vector3(2f, 1f, 2f), ground);

            // 돌길: 시작 지점 → 제단
            for (int i = 0; i < 9; i++)
                Prim(PrimitiveType.Cube, "Path", env, new Vector3((float)(rnd.NextDouble() - 0.5) * 0.5f, 0.02f, -13f + i * 1.9f),
                     new Vector3(1.9f + (float)rnd.NextDouble() * 0.5f, 0.07f, 1.5f), stoneDark, new Vector3(0f, rnd.Next(-8, 8), 0f), false);

            // 봉인의 제단
            var altar = new GameObject("Altar").transform;
            altar.SetParent(env, false);
            altar.localPosition = new Vector3(0f, 0f, 6f);
            Prim(PrimitiveType.Cylinder, "Base", altar, new Vector3(0f, 0.15f, 0f), new Vector3(6f, 0.15f, 6f), stoneDark);
            Prim(PrimitiveType.Cylinder, "Step", altar, new Vector3(0f, 0.4f, 0f), new Vector3(3.6f, 0.12f, 3.6f), stone);
            for (int i = 0; i < 5; i++)
            {
                float a = i * Mathf.PI * 2f / 5f + 0.3f;
                Prim(PrimitiveType.Cube, "Pillar", altar, new Vector3(Mathf.Cos(a) * 2.5f, 1.7f, Mathf.Sin(a) * 2.5f),
                     new Vector3(0.45f, i == 3 ? 2.2f : 3.2f, 0.45f), stone, new Vector3(i == 3 ? 7f : 0f, -a * Mathf.Rad2Deg, 0f));
            }
            Prim(PrimitiveType.Sphere, "Soul Stone", altar, new Vector3(0f, 1.7f, 0f), Vector3.one * 0.7f, soulGlow, default(Vector3), false);
            var altarLight = PointLight("Soul Light", altar, new Vector3(0f, 2.1f, 0f), Soul, 16f, 26f, true);
            altarLight.GetComponent<SoulFlicker>().amount = 0.3f;

            // 납골당 정면 (뒤쪽)
            var crypt = new GameObject("Crypt").transform;
            crypt.SetParent(env, false);
            crypt.localPosition = new Vector3(0f, 0f, 24f);
            Prim(PrimitiveType.Cube, "Body", crypt, new Vector3(0f, 2.6f, 0f), new Vector3(11f, 5.2f, 6f), stone);
            Prim(PrimitiveType.Cube, "Roof", crypt, new Vector3(0f, 5.5f, 0f), new Vector3(12.4f, 0.7f, 7.2f), stoneDark);
            Prim(PrimitiveType.Cube, "Door", crypt, new Vector3(0f, 1.7f, -3.02f), new Vector3(2.4f, 3.4f, 0.1f), Lit("Void", new Color(0.02f, 0.02f, 0.03f)), default(Vector3), false);
            for (int s = -1; s <= 1; s += 2)
                Prim(PrimitiveType.Cylinder, "Column", crypt, new Vector3(s * 2.6f, 2.5f, -3.7f), new Vector3(0.7f, 2.5f, 0.7f), stone);
            PointLight("Crypt Light", crypt, new Vector3(0f, 3f, -5.5f), new Color(0.45f, 1f, 0.6f), 14f, 14f, true);

            // 묘비
            var graves = new GameObject("Graves").transform;
            graves.SetParent(env, false);
            for (int i = 0; i < 70; i++)
            {
                float x = (float)(rnd.NextDouble() * 2 - 1) * 34f, z = (float)(rnd.NextDouble() * 2 - 1) * 30f + 4f;
                if (Mathf.Abs(x) < 3f && z < 3f) continue;                       // 돌길
                if (x * x + (z - 6f) * (z - 6f) < 5f * 5f) continue;             // 제단
                if (Mathf.Abs(x) < 8f && z > 17f) continue;                      // 납골당
                var g = new GameObject("Grave").transform;
                g.SetParent(graves, false);
                g.localPosition = new Vector3(x, 0f, z);
                g.localEulerAngles = new Vector3(rnd.Next(-6, 6), rnd.Next(4) * 90f + rnd.Next(-14, 14), rnd.Next(-9, 9));
                float h = 0.8f + (float)rnd.NextDouble() * 0.7f;
                if (rnd.Next(3) == 0)
                {
                    Prim(PrimitiveType.Cube, "Cross", g, new Vector3(0f, h * 0.7f, 0f), new Vector3(0.16f, h * 1.4f, 0.16f), stone);
                    Prim(PrimitiveType.Cube, "Arm", g, new Vector3(0f, h * 1.0f, 0f), new Vector3(0.7f, 0.16f, 0.16f), stone, default(Vector3), false);
                }
                else
                {
                    Prim(PrimitiveType.Cube, "Slab", g, new Vector3(0f, h * 0.5f, 0f), new Vector3(0.7f, h, 0.16f), stone);
                    Prim(PrimitiveType.Cylinder, "Top", g, new Vector3(0f, h, 0f), new Vector3(0.7f, 0.08f, 0.7f), stone, new Vector3(90f, 0f, 0f), false);
                }
                Prim(PrimitiveType.Cube, "Mound", g, new Vector3(0f, 0.04f, 0.9f), new Vector3(0.9f, 0.12f, 1.7f), stoneDark, default(Vector3), false);
            }

            // 죽은 나무
            var trees = new GameObject("Dead Trees").transform;
            trees.SetParent(env, false);
            for (int i = 0; i < 16; i++)
            {
                float a = (float)rnd.NextDouble() * Mathf.PI * 2f, d = 14f + (float)rnd.NextDouble() * 26f;
                float x = Mathf.Cos(a) * d, z = Mathf.Sin(a) * d + 4f;
                if (Mathf.Abs(x) < 9f && z > 15f) continue;
                float s = 0.9f + (float)rnd.NextDouble() * 0.9f;
                var t = new GameObject("Dead Tree").transform;
                t.SetParent(trees, false);
                t.localPosition = new Vector3(x, 0f, z);
                t.localEulerAngles = new Vector3(rnd.Next(-5, 5), rnd.Next(360), rnd.Next(-5, 5));
                Prim(PrimitiveType.Cylinder, "Trunk", t, new Vector3(0f, 2.2f * s, 0f), new Vector3(0.5f * s, 2.2f * s, 0.5f * s), bark);
                for (int b = 0; b < 5; b++)
                {
                    var pivot = new GameObject("Branch").transform;
                    pivot.SetParent(t, false);
                    pivot.localPosition = new Vector3(0f, (2.2f + b * 0.55f) * s, 0f);
                    pivot.localEulerAngles = new Vector3(0f, b * 72f + rnd.Next(-25, 25), 0f);
                    Prim(PrimitiveType.Cylinder, "B1", pivot, new Vector3(0f, 0.6f * s, 0.8f * s), new Vector3(0.15f * s, 1.05f * s, 0.15f * s), bark, new Vector3(52f, 0f, 0f), false);
                    Prim(PrimitiveType.Cylinder, "B2", pivot, new Vector3(0f, 1.55f * s, 1.65f * s), new Vector3(0.07f * s, 0.6f * s, 0.07f * s), bark, new Vector3(24f, 0f, 0f), false);
                }
            }

            // 영혼 등불: 길 양옆과 묘지 곳곳
            var lanterns = new GameObject("Soul Lanterns").transform;
            lanterns.SetParent(env, false);
            Vector3[] spots =
            {
                new Vector3(-3f, 0f, -9f), new Vector3(3f, 0f, -3f), new Vector3(-3f, 0f, 1f),
                new Vector3(-15f, 0f, 9f), new Vector3(14f, 0f, 12f), new Vector3(-10f, 0f, -14f), new Vector3(17f, 0f, -8f)
            };
            foreach (var p in spots)
            {
                var l = new GameObject("Lantern").transform;
                l.SetParent(lanterns, false);
                l.localPosition = p;
                Prim(PrimitiveType.Cylinder, "Post", l, new Vector3(0f, 1.1f, 0f), new Vector3(0.12f, 1.1f, 0.12f), stoneDark);
                Prim(PrimitiveType.Cube, "Cap", l, new Vector3(0f, 2.62f, 0f), new Vector3(0.5f, 0.08f, 0.5f), stoneDark, default(Vector3), false);
                Prim(PrimitiveType.Sphere, "Flame", l, new Vector3(0f, 2.36f, 0f), Vector3.one * 0.26f, soulGlow, default(Vector3), false);
                PointLight("Light", l, new Vector3(0f, 2.4f, 0f), Soul, 9f, 9f, true);
            }

        }

        static void BuildParticles(Transform parent)
        {
            var mat = LoadOrCreate(LookMatFolder, "SoulParticle", "Necro/SoulParticle", null);
            var mist = LoadOrCreate(LookMatFolder, "GroundMist", "Necro/SoulParticle", m =>
            {
                m.SetColor("_TintColor", new Color(0.5f, 0.42f, 0.85f, 1f));
                m.SetFloat("_Softness", 1.4f);
            });

            // 떠도는 영혼 불티
            var go = new GameObject("Soul Wisps");
            go.transform.SetParent(parent, false);
            go.transform.localPosition = new Vector3(0f, 2.2f, 4f);
            var ps = go.AddComponent<ParticleSystem>();
            var main = ps.main;
            main.loop = true;
            main.prewarm = true;
            main.startLifetime = new ParticleSystem.MinMaxCurve(5f, 10f);
            main.startSpeed = new ParticleSystem.MinMaxCurve(0.02f, 0.25f);
            main.startSize = new ParticleSystem.MinMaxCurve(0.05f, 0.2f);
            main.startColor = new ParticleSystem.MinMaxGradient(new Color(0.8f, 0.55f, 1f, 0.9f), new Color(0.5f, 0.7f, 1f, 0.6f));
            main.maxParticles = 600;
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.gravityModifier = -0.015f;
            var em = ps.emission;
            em.rateOverTime = 55f;
            var sh = ps.shape;
            sh.shapeType = ParticleSystemShapeType.Box;
            sh.scale = new Vector3(70f, 4f, 64f);
            var noise = ps.noise;
            noise.enabled = true;
            noise.strength = 0.35f;
            noise.frequency = 0.25f;
            var col = ps.colorOverLifetime;
            col.enabled = true;
            col.color = new ParticleSystem.MinMaxGradient(FadeInOut());
            if (mat != null) go.GetComponent<ParticleSystemRenderer>().sharedMaterial = mat;

            // 땅안개: 바닥에 누운 큰 원이 천천히 흘러간다
            var mg = new GameObject("Ground Mist");
            mg.transform.SetParent(parent, false);
            mg.transform.localPosition = new Vector3(0f, 0.35f, 4f);
            var mp = mg.AddComponent<ParticleSystem>();
            var mm = mp.main;
            mm.loop = true;
            mm.prewarm = true;
            mm.startLifetime = new ParticleSystem.MinMaxCurve(14f, 24f);
            mm.startSpeed = 0f;
            mm.startSize = new ParticleSystem.MinMaxCurve(7f, 15f);
            mm.startColor = new ParticleSystem.MinMaxGradient(new Color(1f, 1f, 1f, 0.07f), new Color(1f, 1f, 1f, 0.14f));
            mm.maxParticles = 160;
            mm.simulationSpace = ParticleSystemSimulationSpace.World;
            var me = mp.emission;
            me.rateOverTime = 7f;
            var ms = mp.shape;
            ms.shapeType = ParticleSystemShapeType.Box;
            ms.scale = new Vector3(80f, 0.5f, 72f);
            var mv = mp.velocityOverLifetime;
            mv.enabled = true;
            mv.x = new ParticleSystem.MinMaxCurve(0.15f, 0.5f);
            mv.y = new ParticleSystem.MinMaxCurve(0f, 0f);
            mv.z = new ParticleSystem.MinMaxCurve(-0.1f, 0.1f);
            var mc = mp.colorOverLifetime;
            mc.enabled = true;
            mc.color = new ParticleSystem.MinMaxGradient(FadeInOut());
            var mr = mg.GetComponent<ParticleSystemRenderer>();
            mr.renderMode = ParticleSystemRenderMode.HorizontalBillboard;
            if (mist != null) mr.sharedMaterial = mist;
        }

        static Gradient FadeInOut()
        {
            var g = new Gradient();
            g.SetKeys(new[] { new GradientColorKey(Color.white, 0f), new GradientColorKey(Color.white, 1f) },
                      new[] { new GradientAlphaKey(0f, 0f), new GradientAlphaKey(1f, 0.25f), new GradientAlphaKey(1f, 0.7f), new GradientAlphaKey(0f, 1f) });
            return g;
        }

        // 툰 셰이더 비교용 인형 셋: 적(바랜 뼈) / 지배된 망자(영혼 효과) / 금속 갑옷
        static void BuildDummies(Transform parent)
        {
            var root = new GameObject("Toon Test Dummies").transform;
            root.SetParent(parent, false);
            root.localPosition = new Vector3(0f, 0f, -2f);

            Material bone = Toon("Dummy_Bone", new Color(0.86f, 0.82f, 0.72f));
            Material cloth = Toon("Dummy_Cloth", new Color(0.36f, 0.14f, 0.13f));
            Material boneSoul = Toon("Dummy_Bone_Soul", new Color(0.86f, 0.82f, 0.72f), m => m.SetFloat("_Soul", 1f));
            Material clothSoul = Toon("Dummy_Cloth_Soul", new Color(0.36f, 0.14f, 0.13f), m => m.SetFloat("_Soul", 1f));
            Material metal = Toon("Dummy_Metal", new Color(0.42f, 0.44f, 0.52f), m =>
            {
                m.SetFloat("_SpecStrength", 1.2f);
                m.SetFloat("_SpecSize", 0.14f);
                m.SetFloat("_RimStrength", 0.7f);
            });

            var a = BuildMannequin("적 (바랜 뼈)", cloth, bone, bone);
            a.transform.SetParent(root, false);
            a.transform.localPosition = new Vector3(-2.4f, 0f, 0f);
            var b = BuildMannequin("지배된 망자 (영혼 효과)", clothSoul, boneSoul, boneSoul);
            b.transform.SetParent(root, false);
            b.transform.localPosition = new Vector3(0f, 0f, 0f);
            var c = BuildMannequin("금속 갑옷", metal, bone, metal);
            c.transform.SetParent(root, false);
            c.transform.localPosition = new Vector3(2.4f, 0f, 0f);
            foreach (Transform t in root) t.localEulerAngles = new Vector3(0f, 180f, 0f);     // 시작 지점을 바라본다
        }

        // 구·캡슐로 만든 사람 모양 인형 (둥근 면이라 툰 음영과 외곽선이 잘 보인다)
        public static GameObject BuildMannequin(string name, Material body, Material skin, Material head)
        {
            var root = new GameObject(name);
            var t = root.transform;
            Prim(PrimitiveType.Capsule, "Body", t, new Vector3(0f, 0.98f, 0f), new Vector3(0.52f, 0.5f, 0.4f), body, default(Vector3), false);
            Prim(PrimitiveType.Sphere, "Hips", t, new Vector3(0f, 0.72f, 0f), new Vector3(0.6f, 0.5f, 0.46f), body, default(Vector3), false);
            Prim(PrimitiveType.Sphere, "Head", t, new Vector3(0f, 1.6f, 0f), new Vector3(0.36f, 0.38f, 0.36f), skin, default(Vector3), false);
            Prim(PrimitiveType.Sphere, "Hair", t, new Vector3(0f, 1.65f, -0.04f), new Vector3(0.4f, 0.38f, 0.4f), head, default(Vector3), false);
            for (int s = -1; s <= 1; s += 2)
            {
                Prim(PrimitiveType.Capsule, "Arm", t, new Vector3(s * 0.34f, 1.05f, 0f), new Vector3(0.14f, 0.34f, 0.14f), body, new Vector3(0f, 0f, s * 9f), false);
                Prim(PrimitiveType.Sphere, "Hand", t, new Vector3(s * 0.4f, 0.7f, 0f), Vector3.one * 0.13f, skin, default(Vector3), false);
                Prim(PrimitiveType.Capsule, "Leg", t, new Vector3(s * 0.13f, 0.36f, 0f), new Vector3(0.17f, 0.38f, 0.17f), skin, default(Vector3), false);
            }
            return root;
        }

        // ───────────── 툰 셰이더 입히기 ─────────────
        [MenuItem("Tools/Necro/룩/선택한 오브젝트에 툰 셰이더 입히기", priority = 13)]
        public static void ApplyToonToSelection() { ConvertSelection(false); }

        [MenuItem("Tools/Necro/룩/선택한 오브젝트를 지배된 망자로 (영혼 효과)", priority = 14)]
        public static void ApplySoulToSelection() { ConvertSelection(true); }

        static void ConvertSelection(bool soul)
        {
            var toon = FindShader(ToonShaderName);
            if (toon == null) return;
            if (Selection.gameObjects.Length == 0)
            {
                EditorUtility.DisplayDialog("툰 셰이더", "씬(Hierarchy)에서 모델을 먼저 선택하세요. 자식 오브젝트까지 한꺼번에 바뀝니다.", "확인");
                return;
            }
            EnsureFolder(ToonMatFolder);
            var made = new Dictionary<Material, Material>();
            int count = 0, skipped = 0;
            foreach (var go in Selection.gameObjects)
            {
                foreach (var r in go.GetComponentsInChildren<Renderer>(true))
                {
                    if (r is ParticleSystemRenderer) continue;
                    var mats = r.sharedMaterials;
                    bool changed = false;
                    for (int i = 0; i < mats.Length; i++)
                    {
                        var src = mats[i];
                        if (src == null) continue;
                        // VRoid(VRM) 모델의 MToon은 이미 애니풍 셰이더라 그대로 둔다
                        if (src.shader != null && src.shader.name.Contains("MToon")) { skipped++; continue; }
                        Material dst;
                        if (!made.TryGetValue(src, out dst))
                        {
                            dst = MakeToonVariant(src, toon, soul);
                            made[src] = dst;
                        }
                        if (dst != null && dst != src) { mats[i] = dst; changed = true; count++; }
                    }
                    if (changed)
                    {
                        Undo.RecordObject(r, "툰 셰이더 입히기");
                        r.sharedMaterials = mats;
                        EditorUtility.SetDirty(r);
                    }
                }
            }
            AssetDatabase.SaveAssets();
            EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
            Debug.Log("[Necro] 머티리얼 " + count + "개를 " + (soul ? "영혼 효과 툰" : "툰") + " 셰이더로 바꿨어요. 새 머티리얼: " + ToonMatFolder +
                      (skipped > 0 ? " (MToon 머티리얼 " + skipped + "개는 그대로 뒀어요)" : ""));
        }

        static Material MakeToonVariant(Material src, Shader toon, bool soul)
        {
            bool isToon = src.shader == toon;
            if (isToon && !soul) return src;
            if (isToon && src.GetFloat("_Soul") > 0.5f) return src;

            string name = src.name.Replace("/", "_") + (isToon ? "" : "_Toon") + (soul ? "_Soul" : "");
            string path = ToonMatFolder + "/" + name + ".mat";
            var dst = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (dst != null) return dst;

            if (isToon) dst = new Material(src);
            else
            {
                dst = new Material(toon);
                Texture tex = null;
                if (src.HasProperty("_BaseMap")) tex = src.GetTexture("_BaseMap");
                if (tex == null && src.HasProperty("_MainTex")) tex = src.GetTexture("_MainTex");
                if (tex != null) dst.SetTexture("_BaseMap", tex);
                Color c = Color.white;
                if (src.HasProperty("_BaseColor")) c = src.GetColor("_BaseColor");
                else if (src.HasProperty("_Color")) c = src.GetColor("_Color");
                c.a = 1f;
                dst.SetColor("_BaseColor", c);
                if (src.HasProperty("_EmissionColor") && src.IsKeywordEnabled("_EMISSION")) dst.SetColor("_EmissionColor", src.GetColor("_EmissionColor"));
            }
            dst.name = name;
            dst.enableInstancing = true;
            if (soul) dst.SetFloat("_Soul", 1f);
            AssetDatabase.CreateAsset(dst, path);
            return dst;
        }
    }
}
