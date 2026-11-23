using UnityEngine;

namespace Necro
{
    // 전역 바람과 풀 상호작용 값을 셰이더(Necro/Foliage)에 넣는다. 장면에 하나만 둔다.
    //  _NecroWind        xyz: 바람 방향(수평), w: 세기 (잎 끝이 밀리는 거리 m)
    //  _NecroWindParams  x: 흔들림 빈도, y: 돌풍 물결 세기, z: 돌풍 물결 크기(1/m), w: 잔떨림
    //  _NecroInteractPos xyz: 주인공 발 위치, w: 풀이 밀려나는 반지름 (0 이면 꺼짐)
    [DisallowMultipleComponent]
    public class NecroWind : MonoBehaviour
    {
        [Header("바람")]
        [Tooltip("바람이 불어 가는 방향 (도). 위에서 봐서 북쪽(+Z) = 0, 동쪽(+X) = 90")]
        public float direction = 60f;
        [Tooltip("잎 끝이 밀리는 거리 (m). 0.1~0.25 가 자연스럽다")]
        [Range(0f, 1f)] public float strength = 0.14f;
        [Tooltip("흔들림 빈도 (초당 흔들리는 횟수)")]
        [Range(0.05f, 4f)] public float frequency = 0.9f;
        [Tooltip("잎 하나하나가 바르르 떠는 정도")]
        [Range(0f, 1f)] public float flutter = 0.25f;

        [Header("돌풍")]
        [Tooltip("풀밭을 쓸고 지나가는 큰 물결의 세기")]
        [Range(0f, 3f)] public float gustStrength = 0.9f;
        [Tooltip("돌풍 물결 크기 (1/m). 작을수록 물결 하나가 넓다")]
        [Range(0.005f, 0.3f)] public float gustScale = 0.04f;
        [Tooltip("세기가 천천히 오르내리는 폭 (0.5 = ±50%)")]
        [Range(0f, 1f)] public float gustVariation = 0.5f;
        [Tooltip("세기가 한 번 오르내리는 데 걸리는 시간 (초)")]
        [Range(1f, 60f)] public float gustPeriod = 9f;
        [Tooltip("바람 방향이 흔들리는 폭 (도)")]
        [Range(0f, 90f)] public float directionWander = 18f;

        [Header("상호작용 (주인공 주변 풀이 밀려남)")]
        [Tooltip("주인공. 비워 두면 시작할 때 이름이 'Player' 인 오브젝트를 한 번 찾는다")]
        public Transform hero;
        [Tooltip("풀이 밀려나는 반지름 (m). 0 이면 끈다")]
        [Range(0f, 4f)] public float interactRadius = 1.1f;

        static readonly int WindId = Shader.PropertyToID("_NecroWind");
        static readonly int ParamsId = Shader.PropertyToID("_NecroWindParams");
        static readonly int InteractId = Shader.PropertyToID("_NecroInteractPos");

        float seed;

        // 다른 효과(입자 흐름 등)가 같은 바람을 쓰도록 공개한다
        public Vector3 CurrentDirection { get; private set; }
        public float CurrentStrength { get; private set; }

        void Awake()
        {
            seed = Random.value * 100f;
            CurrentDirection = Vector3.forward;
        }

        void Start()
        {
            if (hero == null)
            {
                var p = GameObject.Find("Player");     // Start 에서 한 번만 찾는다
                if (p != null) hero = p.transform;
            }
            Push();
        }

        void OnEnable() { Push(); }

        void OnDisable()
        {
            Shader.SetGlobalVector(WindId, Vector4.zero);
            Shader.SetGlobalVector(InteractId, Vector4.zero);
        }

        void Update() { Push(); }

        void Push()
        {
            float t = Time.time;
            // 세기: 두 가지 느린 노이즈를 섞어 규칙적으로 보이지 않게 한다
            float n = Mathf.PerlinNoise(t / Mathf.Max(gustPeriod, 0.1f), seed) * 0.7f +
                      Mathf.PerlinNoise(t / Mathf.Max(gustPeriod * 0.37f, 0.1f), seed + 7.3f) * 0.3f;
            float s = strength * Mathf.Max(0f, 1f + (n - 0.5f) * 2f * gustVariation);
            float wander = (Mathf.PerlinNoise(seed + 3.1f, t / Mathf.Max(gustPeriod * 2.3f, 0.1f)) - 0.5f) * 2f * directionWander;
            float a = (direction + wander) * Mathf.Deg2Rad;
            var dir = new Vector3(Mathf.Sin(a), 0f, Mathf.Cos(a));
            CurrentDirection = dir;
            CurrentStrength = s;

            Shader.SetGlobalVector(WindId, new Vector4(dir.x, 0f, dir.z, s));
            Shader.SetGlobalVector(ParamsId, new Vector4(frequency, gustStrength * (0.6f + n * 0.8f), gustScale, flutter));
            if (hero != null && interactRadius > 0f)
            {
                Vector3 p = hero.position;
                Shader.SetGlobalVector(InteractId, new Vector4(p.x, p.y, p.z, interactRadius));
            }
            else Shader.SetGlobalVector(InteractId, Vector4.zero);
        }
    }
}
