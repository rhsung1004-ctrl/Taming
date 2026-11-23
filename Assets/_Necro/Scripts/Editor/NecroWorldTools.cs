using System.Collections.Generic;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Necro.EditorTools
{
    // Tools → Necro → 월드 → 2. URP 설정 맞추기
    // 오픈월드에 맞게 URP 에셋과 렌더러 데이터를 고친다:
    //   Forward+ (등불·도깨비불 같은 점광원이 많아도 물체마다 4개 제한이 없다), 그림자 거리 150m · 캐스케이드 4,
    //   깊이 텍스처 켬 + 깊이 복사를 불투명 다음에 (물가가 옅어지는 물 셰이더가 읽는다), HDR 켬 (영혼 발광 블룸).
    // 필드 이름은 URP 6000.0 소스(UniversalRenderPipelineAsset.cs, UniversalRendererData.cs)의 직렬화 이름이다.
    // 공개 설정자가 없는(internal) 값도 있어 SerializedObject 로 고친다. 못 찾은 필드는 경고로 알린다.
    public static class NecroWorldTools
    {
        [MenuItem("Tools/Necro/월드/2. URP 설정 맞추기", priority = 102)]
        public static void SetupUrp()
        {
            var assets = new List<UniversalRenderPipelineAsset>();
            AddAsset(assets, GraphicsSettings.defaultRenderPipeline);
            AddAsset(assets, GraphicsSettings.currentRenderPipeline);
            foreach (var a in GraphicsSettings.allConfiguredRenderPipelines) AddAsset(assets, a);
            if (assets.Count == 0)
            {
                EditorUtility.DisplayDialog("URP 설정 맞추기",
                    "URP 에셋을 찾지 못했어요.\nEdit → Project Settings → Graphics 에 URP 에셋이 들어 있는지 확인해 주세요.", "확인");
                return;
            }

            var log = new List<string>();
            var missing = new List<string>();
            var renderers = new List<ScriptableObject>();
            foreach (var asset in assets)
            {
                var so = new SerializedObject(asset);
                string who = asset.name + ": ";
                SetEnum(so, "m_MainLightRenderingMode", 1, who, log, missing);            // PerPixel
                SetBool(so, "m_MainLightShadowsSupported", true, who, log, missing);
                SetEnum(so, "m_MainLightShadowmapResolution", 4096, who, log, missing);   // 캐스케이드 4개가 한 장을 나눠 쓴다
                SetEnum(so, "m_AdditionalLightsRenderingMode", 1, who, log, missing);      // PerPixel
                SetFloat(so, "m_ShadowDistance", 150f, who, log, missing);
                SetInt(so, "m_ShadowCascadeCount", 4, who, log, missing);
                SetVector3(so, "m_Cascade4Split", new Vector3(0.067f, 0.2f, 0.467f), who, log, missing);   // 10 / 30 / 70 / 150 m
                SetFloat(so, "m_CascadeBorder", 0.2f, who, log, missing);
                SetBool(so, "m_SoftShadowsSupported", true, who, log, missing);
                SetBool(so, "m_AnyShadowsSupported", true, who, log, missing);
                SetBool(so, "m_RequireDepthTexture", true, who, log, missing);
                SetBool(so, "m_SupportsHDR", true, who, log, missing);
                SetBool(so, "m_EnableLODCrossFade", true, who, log, missing);              // LOD 전환을 디더로 부드럽게
                SetBool(so, "m_UseSRPBatcher", true, who, log, missing);
                so.ApplyModifiedPropertiesWithoutUndo();
                EditorUtility.SetDirty(asset);

                var list = so.FindProperty("m_RendererDataList");
                if (list == null) { missing.Add(who + "m_RendererDataList"); continue; }
                for (int i = 0; i < list.arraySize; i++)
                {
                    var rd = list.GetArrayElementAtIndex(i).objectReferenceValue as ScriptableObject;
                    if (rd != null && !renderers.Contains(rd)) renderers.Add(rd);
                }
            }

            int urd = 0;
            foreach (var rd in renderers)
            {
                if (!(rd is UniversalRendererData)) continue;      // 2D 렌더러 등은 건너뛴다
                urd++;
                var so = new SerializedObject(rd);
                string who = rd.name + ": ";
                SetEnum(so, "m_RenderingMode", 2, who, log, missing);      // RenderingMode.ForwardPlus = 2
                SetEnum(so, "m_CopyDepthMode", 0, who, log, missing);      // CopyDepthMode.AfterOpaques = 0 (물 셰이더가 투명 큐에서 깊이를 읽는다)
                so.ApplyModifiedPropertiesWithoutUndo();
                EditorUtility.SetDirty(rd);
            }
            AssetDatabase.SaveAssets();

            string names = "";
            foreach (var a in assets) names += (names.Length > 0 ? ", " : "") + a.name;
            Debug.Log("[Necro] URP 설정을 맞췄어요. URP 에셋 " + assets.Count + "개 (" + names + "), 렌더러 " + urd + "개\n" +
                      (log.Count > 0 ? "바꾼 것:\n" + string.Join("\n", log.ToArray()) : "바꿀 것이 없었어요 (이미 맞춰져 있음)"));
            if (missing.Count > 0)
                Debug.LogWarning("[Necro] URP 설정 중 찾지 못한 필드 (URP 버전이 달라 이름이 바뀌었을 수 있어요 — Inspector 에서 직접 맞춰 주세요):\n" +
                                 string.Join("\n", missing.ToArray()));
            if (urd == 0)
                Debug.LogWarning("[Necro] Universal Renderer 데이터를 찾지 못해 Forward+ 와 깊이 복사 시점은 바꾸지 못했어요.");
        }

        static void AddAsset(List<UniversalRenderPipelineAsset> list, RenderPipelineAsset a)
        {
            var u = a as UniversalRenderPipelineAsset;
            if (u != null && !list.Contains(u)) list.Add(u);
        }

        static SerializedProperty Find(SerializedObject so, string field, string who, List<string> missing)
        {
            var p = so.FindProperty(field);
            if (p == null) missing.Add(who + field);
            return p;
        }

        static void SetFloat(SerializedObject so, string field, float v, string who, List<string> log, List<string> missing)
        {
            var p = Find(so, field, who, missing);
            if (p == null || Mathf.Approximately(p.floatValue, v)) return;
            log.Add(who + field + ": " + p.floatValue + " → " + v);
            p.floatValue = v;
        }

        static void SetInt(SerializedObject so, string field, int v, string who, List<string> log, List<string> missing)
        {
            var p = Find(so, field, who, missing);
            if (p == null || p.intValue == v) return;
            log.Add(who + field + ": " + p.intValue + " → " + v);
            p.intValue = v;
        }

        // 열거형은 실제 값(intValue)으로 넣는다 (RenderingMode 처럼 값이 순서와 다른 것이 있다)
        static void SetEnum(SerializedObject so, string field, int v, string who, List<string> log, List<string> missing)
        {
            SetInt(so, field, v, who, log, missing);
        }

        static void SetBool(SerializedObject so, string field, bool v, string who, List<string> log, List<string> missing)
        {
            var p = Find(so, field, who, missing);
            if (p == null || p.boolValue == v) return;
            log.Add(who + field + ": " + p.boolValue + " → " + v);
            p.boolValue = v;
        }

        static void SetVector3(SerializedObject so, string field, Vector3 v, string who, List<string> log, List<string> missing)
        {
            var p = Find(so, field, who, missing);
            if (p == null || (p.vector3Value - v).sqrMagnitude < 1e-8f) return;
            log.Add(who + field + ": " + p.vector3Value + " → " + v);
            p.vector3Value = v;
        }
    }
}
