using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Taming.EditorTools
{
    // 애니메이션 FBX 가져오기 자동 설정: Humanoid + 반복 클립 지정
    public class TamingAnimationPostprocessor : AssetPostprocessor
    {
        public const string AnimRoot = "Assets/_Taming/Art/Animations/";

        void OnPreprocessModel()
        {
            if (!assetPath.StartsWith(AnimRoot)) return;
            var mi = (ModelImporter)assetImporter;
            mi.animationType = ModelImporterAnimationType.Human;
            mi.importAnimation = true;
        }

        void OnPreprocessAnimation()
        {
            if (!assetPath.StartsWith(AnimRoot)) return;
            var mi = (ModelImporter)assetImporter;
            var clips = mi.defaultClipAnimations;
            if (clips == null || clips.Length == 0) return;
            foreach (var c in clips)
            {
                string n = c.name.ToLower();
                c.loopTime = n.Contains("loop") || n.Contains("idle") || n.Contains("walk") || n.Contains("run") ||
                             n.Contains("jog") || n.Contains("sprint") || n.Contains("fall");
                c.lockRootRotation = true;
                c.lockRootHeightY = true;
                c.lockRootPositionXZ = true;
                c.keepOriginalOrientation = true;
                c.keepOriginalPositionY = true;
                c.keepOriginalPositionXZ = true;
            }
            mi.clipAnimations = clips;
        }
    }

    public static class TamingSetupTools
    {
        const string SettingsFolder = "Assets/_Taming/Settings";
        const string PlayerAnimFolder = "Assets/_Taming/Art/Animations/Player";
        const string PlayerControllerPath = "Assets/_Taming/Settings/PlayerAnimator.controller";

        static void EnsureFolder(string path)
        {
            if (AssetDatabase.IsValidFolder(path)) return;
            string parent = Path.GetDirectoryName(path).Replace('\\', '/');
            EnsureFolder(parent);
            AssetDatabase.CreateFolder(parent, Path.GetFileName(path));
        }

        [MenuItem("Tools/Taming/0. 폴더 구조 만들기", priority = 0)]
        public static void MakeFolders()
        {
            string[] folders =
            {
                "Assets/_Taming/Art/Characters/Player",
                "Assets/_Taming/Art/Animations/Player",
                "Assets/_Taming/Art/Monsters",
                "Assets/_Taming/Art/Environment",
                "Assets/_Taming/Art/VFX",
                "Assets/_Taming/Data/Monsters",
                "Assets/_Taming/Prefabs",
                "Assets/_Taming/Scenes",
                SettingsFolder
            };
            foreach (var f in folders) EnsureFolder(f);
            AssetDatabase.Refresh();
            Debug.Log("[Taming] 폴더 구조를 만들었어요.");
        }

        // ───────────── 룩 (조명·후처리) ─────────────
        [MenuItem("Tools/Taming/1. 룩 기본 세팅 (조명·후처리)", priority = 10)]
        public static void SetupLook()
        {
            EnsureFolder(SettingsFolder);
            string profilePath = SettingsFolder + "/LookProfile.asset";
            var profile = AssetDatabase.LoadAssetAtPath<VolumeProfile>(profilePath);
            if (profile == null)
            {
                profile = ScriptableObject.CreateInstance<VolumeProfile>();
                AssetDatabase.CreateAsset(profile, profilePath);

                var bloom = profile.Add<Bloom>(true);
                bloom.intensity.Override(0.7f);
                bloom.threshold.Override(1.05f);
                bloom.scatter.Override(0.65f);
                AssetDatabase.AddObjectToAsset(bloom, profile);

                var tone = profile.Add<Tonemapping>(true);
                tone.mode.Override(TonemappingMode.Neutral);
                AssetDatabase.AddObjectToAsset(tone, profile);

                var color = profile.Add<ColorAdjustments>(true);
                color.postExposure.Override(0.2f);
                color.contrast.Override(6f);
                color.saturation.Override(16f);
                AssetDatabase.AddObjectToAsset(color, profile);

                var wb = profile.Add<WhiteBalance>(true);
                wb.temperature.Override(5f);
                AssetDatabase.AddObjectToAsset(wb, profile);

                var vig = profile.Add<Vignette>(true);
                vig.intensity.Override(0.16f);
                AssetDatabase.AddObjectToAsset(vig, profile);

                EditorUtility.SetDirty(profile);
                AssetDatabase.SaveAssets();
            }

            var volGo = GameObject.Find("Taming Look Volume");
            if (volGo == null)
            {
                volGo = new GameObject("Taming Look Volume");
                Undo.RegisterCreatedObjectUndo(volGo, "Look Volume");
            }
            var vol = volGo.GetComponent<Volume>();
            if (vol == null) vol = Undo.AddComponent<Volume>(volGo);
            vol.isGlobal = true;
            vol.priority = 10f;
            vol.sharedProfile = profile;

            var cam = Camera.main;
            if (cam != null)
            {
                var data = cam.GetComponent<UniversalAdditionalCameraData>();
                if (data == null) data = Undo.AddComponent<UniversalAdditionalCameraData>(cam.gameObject);
                data.renderPostProcessing = true;
                data.antialiasing = AntialiasingMode.FastApproximateAntialiasing;
                cam.farClipPlane = 1500f;
            }

            Light sun = null;
#if UNITY_2023_1_OR_NEWER
            var lights = Object.FindObjectsByType<Light>(FindObjectsSortMode.None);
#else
            var lights = Object.FindObjectsOfType<Light>();
#endif
            foreach (var l in lights) if (l.type == LightType.Directional) sun = l;
            if (sun == null)
            {
                var go = new GameObject("Sun");
                Undo.RegisterCreatedObjectUndo(go, "Sun");
                sun = go.AddComponent<Light>();
                sun.type = LightType.Directional;
            }
            Undo.RecordObject(sun, "Sun");
            Undo.RecordObject(sun.transform, "Sun");
            sun.transform.rotation = Quaternion.Euler(42f, -38f, 0f);
            sun.color = new Color(1f, 0.95f, 0.86f);
            sun.intensity = 1.35f;
            sun.shadows = LightShadows.Soft;
            RenderSettings.sun = sun;

            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.66f, 0.76f, 0.95f);
            RenderSettings.ambientEquatorColor = new Color(0.6f, 0.66f, 0.68f);
            RenderSettings.ambientGroundColor = new Color(0.38f, 0.36f, 0.32f);
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.Linear;
            RenderSettings.fogColor = new Color(0.74f, 0.85f, 0.97f);
            RenderSettings.fogStartDistance = 120f;
            RenderSettings.fogEndDistance = 900f;

            EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
            Debug.Log("[Taming] 룩 기본 세팅 완료: 블룸, 색 보정, 비네트, 따뜻한 햇빛, 하늘색 대기 원근. 값은 Settings/LookProfile에서 조정하세요.");
        }

        // ───────────── 플레이어 ─────────────
        [MenuItem("Tools/Taming/2. 선택한 모델로 플레이어 만들기", priority = 20)]
        public static void CreatePlayer()
        {
            var model = Selection.activeGameObject;
            if (model == null || EditorUtility.IsPersistent(model))
            {
                EditorUtility.DisplayDialog("플레이어 만들기",
                    "씬(Hierarchy)에 놓인 주인공 모델을 먼저 선택하세요.\n(VRoid → UniVRM으로 가져온 모델을 씬에 끌어다 놓은 뒤 선택)", "확인");
                return;
            }

            var root = new GameObject("Player");
            Undo.RegisterCreatedObjectUndo(root, "Create Player");
            root.transform.position = model.transform.position;
            root.transform.rotation = model.transform.rotation;
            Undo.SetTransformParent(model.transform, root.transform, "Create Player");
            model.transform.localPosition = Vector3.zero;
            model.transform.localRotation = Quaternion.identity;

            float height = 1.6f;
            Bounds b;
            if (Measure(model, out b)) height = Mathf.Max(0.8f, b.size.y);

            var cc = root.AddComponent<CharacterController>();
            cc.height = height * 0.95f;
            cc.radius = Mathf.Clamp(height * 0.17f, 0.2f, 0.4f);
            cc.center = new Vector3(0f, cc.height * 0.5f + cc.skinWidth, 0f);
            cc.stepOffset = 0.35f;
            cc.slopeLimit = 50f;

            var input = root.AddComponent<PlayerInputReader>();
            var motor = root.AddComponent<PlayerMotor>();
            motor.input = input;
            var bridge = root.AddComponent<PlayerAnimatorBridge>();
            bridge.motor = motor;

            var animator = model.GetComponentInChildren<Animator>();
            if (animator != null)
            {
                animator.applyRootMotion = false;
                var ctrl = AssetDatabase.LoadAssetAtPath<RuntimeAnimatorController>(PlayerControllerPath);
                if (ctrl != null) animator.runtimeAnimatorController = ctrl;
                bridge.animator = animator;
            }

            var cam = Camera.main;
            if (cam == null)
            {
                var camGo = new GameObject("Main Camera");
                Undo.RegisterCreatedObjectUndo(camGo, "Camera");
                camGo.tag = "MainCamera";
                cam = camGo.AddComponent<Camera>();
            }
            var orbit = cam.GetComponent<OrbitCamera>();
            if (orbit == null) orbit = Undo.AddComponent<OrbitCamera>(cam.gameObject);
            orbit.target = root.transform;
            orbit.input = input;
            orbit.pivotOffset = new Vector3(0f, height * 0.88f, 0f);
            motor.cameraTransform = cam.transform;

            Selection.activeGameObject = root;
            EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
            Debug.Log("[Taming] 플레이어 생성 완료 (키 " + height.ToString("0.00") + "m)." +
                      (animator == null ? " 모델에 Animator가 없어요 — Humanoid 모델인지 확인하세요." : ""));
        }

        static bool Measure(GameObject g, out Bounds b)
        {
            b = new Bounds();
            bool any = false;
            foreach (var r in g.GetComponentsInChildren<Renderer>())
            {
                if (!any) { b = r.bounds; any = true; }
                else b.Encapsulate(r.bounds);
            }
            return any;
        }

        // ───────────── 애니메이터 ─────────────
        static AnimationClip Pick(List<AnimationClip> clips, params string[] keys)
        {
            foreach (var k in keys)
            {
                AnimationClip best = null;
                foreach (var c in clips)
                    if (c.name.ToLower().Contains(k) && (best == null || c.name.Length < best.name.Length)) best = c;
                if (best != null) return best;
            }
            return null;
        }

        [MenuItem("Tools/Taming/3. 플레이어 애니메이터 만들기", priority = 30)]
        public static void BuildPlayerAnimator()
        {
            EnsureFolder(PlayerAnimFolder);
            EnsureFolder(SettingsFolder);
            var clips = new List<AnimationClip>();
            var seen = new HashSet<string>();
            foreach (var guid in AssetDatabase.FindAssets("t:AnimationClip", new[] { PlayerAnimFolder }))
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                if (!seen.Add(path)) continue;
                foreach (var a in AssetDatabase.LoadAllAssetsAtPath(path))
                {
                    var c = a as AnimationClip;
                    if (c != null && !c.name.StartsWith("__preview__")) clips.Add(c);
                }
            }
            if (clips.Count == 0)
            {
                EditorUtility.DisplayDialog("플레이어 애니메이터",
                    PlayerAnimFolder + " 폴더에 애니메이션 FBX를 먼저 넣어 주세요.\n(대기 idle, 걷기 walk, 달리기 run/jog, 점프 jump, 낙하 fall)", "확인");
                return;
            }

            var idle = Pick(clips, "idle") ?? clips[0];
            var walk = Pick(clips, "walk") ?? idle;
            var run = Pick(clips, "jog", "run") ?? walk;
            var sprint = Pick(clips, "sprint");
            var jumpStart = Pick(clips, "jump_start", "jumpstart", "jump start", "jump_up");
            var fall = Pick(clips, "fall", "jump_loop", "jumploop", "jump loop", "air", "jump") ?? idle;

            if (AssetDatabase.LoadAssetAtPath<Object>(PlayerControllerPath) != null)
            {
                if (!EditorUtility.DisplayDialog("플레이어 애니메이터", "기존 PlayerAnimator를 새로 만들까요? (직접 고친 내용은 사라집니다)", "새로 만들기", "취소"))
                    return;
                AssetDatabase.DeleteAsset(PlayerControllerPath);
            }

            var ctrl = AnimatorController.CreateAnimatorControllerAtPath(PlayerControllerPath);
            ctrl.AddParameter("Speed", AnimatorControllerParameterType.Float);
            ctrl.AddParameter("Grounded", AnimatorControllerParameterType.Bool);
            ctrl.AddParameter("VerticalSpeed", AnimatorControllerParameterType.Float);
            ctrl.AddParameter("Jump", AnimatorControllerParameterType.Trigger);

            BlendTree tree;
            var loco = ctrl.CreateBlendTreeInController("Locomotion", out tree, 0);
            tree.blendType = BlendTreeType.Simple1D;
            tree.blendParameter = "Speed";
            tree.useAutomaticThresholds = false;
            tree.AddChild(idle, 0f);
            tree.AddChild(walk, 2.4f);
            tree.AddChild(run, 5.6f);
            if (sprint != null) tree.AddChild(sprint, 8.5f);

            var sm = ctrl.layers[0].stateMachine;
            var air = sm.AddState("Airborne");
            air.motion = fall;

            var toAir = loco.AddTransition(air);
            toAir.hasExitTime = false;
            toAir.duration = 0.12f;
            toAir.AddCondition(AnimatorConditionMode.IfNot, 0f, "Grounded");

            var land = air.AddTransition(loco);
            land.hasExitTime = false;
            land.duration = 0.1f;
            land.AddCondition(AnimatorConditionMode.If, 0f, "Grounded");

            if (jumpStart != null)
            {
                var js = sm.AddState("JumpStart");
                js.motion = jumpStart;
                var toJump = loco.AddTransition(js);
                toJump.hasExitTime = false;
                toJump.duration = 0.05f;
                toJump.AddCondition(AnimatorConditionMode.If, 0f, "Jump");
                var jsToAir = js.AddTransition(air);
                jsToAir.hasExitTime = true;
                jsToAir.exitTime = 0.85f;
                jsToAir.duration = 0.1f;
            }
            sm.defaultState = loco;

            AssetDatabase.SaveAssets();

            // 씬의 플레이어에 바로 연결
#if UNITY_2023_1_OR_NEWER
            var bridges = Object.FindObjectsByType<PlayerAnimatorBridge>(FindObjectsSortMode.None);
#else
            var bridges = Object.FindObjectsOfType<PlayerAnimatorBridge>();
#endif
            foreach (var br in bridges)
            {
                var an = br.animator != null ? br.animator : br.GetComponentInChildren<Animator>();
                if (an == null) continue;
                Undo.RecordObject(an, "Assign Controller");
                an.runtimeAnimatorController = ctrl;
            }

            Debug.Log("[Taming] PlayerAnimator 생성: 대기=" + idle.name + ", 걷기=" + walk.name + ", 달리기=" + run.name +
                      (sprint != null ? ", 질주=" + sprint.name : "") + (jumpStart != null ? ", 점프=" + jumpStart.name : "") + ", 공중=" + fall.name);
        }
    }
}
