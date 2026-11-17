using UnityEngine;

namespace Necro
{
    // 영혼 등불의 일렁임: 광원 세기를 부드럽게 흔든다. 묘지 등불, 제단, 영혼석에 붙인다.
    [RequireComponent(typeof(Light))]
    public class SoulFlicker : MonoBehaviour
    {
        [Header("일렁임")]
        [Tooltip("세기가 흔들리는 폭 (0.2 = 기준 세기의 ±20%)")] [Range(0f, 1f)] public float amount = 0.22f;
        [Tooltip("흔들리는 빠르기")] public float speed = 2.2f;
        [Tooltip("위아래로 떠다니는 높이 (m). 0이면 움직이지 않는다")] public float bobHeight = 0f;

        Light cached;
        float baseIntensity, seed;
        Vector3 basePos;

        void Awake()
        {
            cached = GetComponent<Light>();
            baseIntensity = cached.intensity;
            basePos = transform.localPosition;
            seed = Random.value * 100f;
        }

        void Update()
        {
            float t = Time.time * speed + seed;
            // 두 가지 느린 흔들림을 섞어 규칙적으로 보이지 않게 한다
            float n = Mathf.PerlinNoise(t, seed) * 0.7f + Mathf.PerlinNoise(t * 2.7f, seed + 9f) * 0.3f;
            cached.intensity = baseIntensity * (1f + (n - 0.5f) * 2f * amount);
            if (bobHeight > 0f) transform.localPosition = basePos + Vector3.up * (Mathf.Sin(t * 0.6f) * bobHeight);
        }
    }
}
