using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Necro
{
    // 분위기 한 벌: 달빛, 주변광, 안개, 하늘, 색 보정
    [System.Serializable]
    public class LookPreset
    {
        [Tooltip("화면 위에 보이는 프리셋 이름")] public string name = "이름";

        [Header("달빛")]
        [Tooltip("달빛(방향광) 색")] public Color moonColor = new Color(0.62f, 0.7f, 1f);
        [Tooltip("달빛(방향광) 세기")] public float moonIntensity = 1.25f;
        [Tooltip("달빛 방향 (X: 높이 각도, Y: 방위)")] public Vector2 moonAngles = new Vector2(38f, -150f);

        [Header("주변광")]
        [Tooltip("위에서 오는 주변광 색 (하늘 쪽)")] public Color ambientSky = new Color(0.2f, 0.2f, 0.36f);
        [Tooltip("옆에서 오는 주변광 색 (지평선 쪽)")] public Color ambientEquator = new Color(0.17f, 0.14f, 0.27f);
        [Tooltip("아래에서 오는 주변광 색 (땅 쪽)")] public Color ambientGround = new Color(0.07f, 0.06f, 0.11f);

        [Header("안개와 하늘")]
        [Tooltip("안개 색이자 하늘의 지평선 색")] public Color fogColor = new Color(0.16f, 0.12f, 0.27f);
        [Tooltip("안개 짙기 (지수 제곱). 1장 오픈월드 만들기 도구가 world.json 안개 비율에 맞춰 모든 프리셋을 줄여 넣는다")] public float fogDensity = 0.016f;
        [Tooltip("하늘 꼭대기 색 (Necro/Sky 의 _TopColor)")] public Color skyTop = new Color(0.02f, 0.02f, 0.07f);
        [Tooltip("달 원반 색 (HDR, 1 을 넘으면 번져 보인다)")] [ColorUsage(false, true)] public Color moonDisc = new Color(1.5f, 1.6f, 2.2f);
        [Tooltip("별 밝기 (0 이면 별이 없다)")] public float starBrightness = 1.4f;

        [Header("색 보정")]
        [Tooltip("후처리 노출 (EV). 높을수록 화면 전체가 밝다")] public float exposure = 0.25f;
        [Tooltip("후처리 채도 (-100 ~ 100). 음수면 색이 빠진다")] public float saturation = 10f;
        [Tooltip("어두운 곳에 입히는 색 (Split Toning 의 그림자 색)")] public Color shadowTint = new Color(0.42f, 0.34f, 0.62f);
    }

    // 룩 테스트용: 플레이 중 F3을 누르면 분위기 프리셋을 차례로 바꿔 가며 비교한다.
    // 마음에 드는 프리셋이 정해지면 그 값을 기본으로 굳히고 이 컴포넌트는 뗀다.
    public class LookPresetCycler : MonoBehaviour
    {
        [Header("참조")]
        [Tooltip("달빛(방향광). 프리셋의 색·세기·방향을 넣는다")] public Light moon;
        [Tooltip("후처리 볼륨. 프로필의 Color Adjustments·Split Toning 을 프리셋 값으로 바꾼다")] public Volume volume;

        [Header("프리셋 (F3으로 넘김)")]
        [Tooltip("비교할 분위기 목록. F3 을 누를 때마다 다음 것으로 바뀐다")] public LookPreset[] presets;
        [Tooltip("지금 쓰는 프리셋 번호 (0 부터)")] public int index;

        Material sky;
        ColorAdjustments color;
        SplitToning split;
        float labelUntil;
        GUIStyle style;
        string labelShown, labelHint;   // 화면 표시 문자열. Apply 에서 한 번 만들어 OnGUI 에서는 할당하지 않는다

        void Start()
        {
            // 에셋을 직접 고치지 않도록 하늘 머티리얼과 후처리 프로필은 복사본을 쓴다
            if (RenderSettings.skybox != null)
            {
                sky = new Material(RenderSettings.skybox);
                RenderSettings.skybox = sky;
            }
            if (volume != null && volume.profile != null)
            {
                volume.profile.TryGet(out color);
                volume.profile.TryGet(out split);
            }
            Apply();
        }

        void Update()
        {
            var k = Keyboard.current;
            if (k == null || presets == null || presets.Length == 0) return;
            if (k.f3Key.wasPressedThisFrame)
            {
                index = (index + 1) % presets.Length;
                Apply();
            }
        }

        public void Apply()
        {
            if (presets == null || presets.Length == 0) return;
            index = Mathf.Clamp(index, 0, presets.Length - 1);
            var p = presets[index];

            if (moon != null)
            {
                moon.color = p.moonColor;
                moon.intensity = p.moonIntensity;
                moon.transform.rotation = Quaternion.Euler(p.moonAngles.x, p.moonAngles.y, 0f);
            }
            RenderSettings.ambientSkyColor = p.ambientSky;
            RenderSettings.ambientEquatorColor = p.ambientEquator;
            RenderSettings.ambientGroundColor = p.ambientGround;
            RenderSettings.fogColor = p.fogColor;
            RenderSettings.fogDensity = p.fogDensity;

            if (sky != null)
            {
                sky.SetColor("_HorizonColor", p.fogColor);
                sky.SetColor("_TopColor", p.skyTop);
                sky.SetColor("_MoonColor", p.moonDisc);
                sky.SetFloat("_StarBrightness", p.starBrightness);
                if (moon != null)
                {
                    Vector3 d = -moon.transform.forward;
                    sky.SetVector("_MoonDir", new Vector4(d.x, d.y, d.z, 0f));
                }
            }
            if (color != null)
            {
                color.postExposure.Override(p.exposure);
                color.saturation.Override(p.saturation);
            }
            if (split != null) split.shadows.Override(p.shadowTint);

            BuildLabels();
            labelUntil = Time.unscaledTime + 4f;
        }

        void BuildLabels()
        {
            string n = presets[index].name;
            labelShown = "분위기 " + (index + 1) + " / " + presets.Length + " — " + n + "   [F3] 다음";
            labelHint = "[F3] 분위기 바꾸기 (" + n + ")";
        }

        // 테스트용 표시 (본편 UI가 아니다)
        void OnGUI()
        {
            if (presets == null || presets.Length == 0) return;
            if (style == null)
            {
                style = new GUIStyle(GUI.skin.label);
                style.fontSize = 22;
                style.fontStyle = FontStyle.Bold;
                style.alignment = TextAnchor.UpperCenter;
            }
            if (labelShown == null) { index = Mathf.Clamp(index, 0, presets.Length - 1); BuildLabels(); }   // Apply 전에 그려질 때만 (한 번)
            bool show = Time.unscaledTime < labelUntil;
            style.normal.textColor = new Color(1f, 1f, 1f, show ? 1f : 0.45f);
            GUI.Label(new Rect(0f, 14f, Screen.width, 40f), show ? labelShown : labelHint, style);
        }
    }
}
