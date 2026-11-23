using UnityEngine;

namespace Necro
{
    // 주변 효과(영혼 불티, 땅안개, 반딧불 같은 입자)를 주인공 주변에 따라다니게 한다.
    // 자식 입자 시스템은 월드 공간으로 방출하므로, 이 오브젝트가 움직여도 이미 나온 입자는 제자리에 남고
    // 방출 영역만 주인공을 따라간다. 넓은 오픈월드 전체에 입자를 깔지 않아도 어디서나 분위기가 난다.
    public class AmbientFollower : MonoBehaviour
    {
        [Header("따라갈 대상")]
        [Tooltip("주인공. 비워 두면 시작할 때 이름이 'Player' 인 오브젝트를 한 번 찾는다")]
        public Transform target;
        [Tooltip("대상 위치에서 더할 오프셋 (m)")]
        public Vector3 offset = Vector3.zero;

        [Header("움직임")]
        [Tooltip("이 거리(m) 이상 벌어졌을 때만 따라간다. 방출 영역이 매 프레임 떨리지 않게")]
        [Range(0f, 5f)] public float step = 0.75f;
        [Tooltip("카메라가 보는 쪽으로 방출 영역을 이만큼(m) 앞당긴다. 화면 안에 입자가 더 많이 보인다")]
        [Range(0f, 40f)] public float lookAhead = 8f;

        [Header("세기")]
        [Tooltip("자식 입자들의 방출량 배율 (0 이면 멈춤). 지역마다 바꿔 쓴다")]
        [Range(0f, 3f)] public float emissionScale = 1f;

        Transform cam;
        ParticleSystem[] systems;
        float[] baseRates;
        float appliedScale = -1f;

        void Start()
        {
            if (target == null)
            {
                var p = GameObject.Find("Player");     // Start 에서 한 번만 찾는다
                if (p != null) target = p.transform;
            }
            if (Camera.main != null) cam = Camera.main.transform;
            systems = GetComponentsInChildren<ParticleSystem>(true);
            baseRates = new float[systems.Length];
            for (int i = 0; i < systems.Length; i++) baseRates[i] = systems[i].emission.rateOverTimeMultiplier;
            Snap();
        }

        void LateUpdate()
        {
            if (target == null) return;
            Vector3 want = Desired();
            if ((want - transform.position).sqrMagnitude > step * step) transform.position = want;
            if (!Mathf.Approximately(appliedScale, emissionScale)) ApplyScale();
        }

        Vector3 Desired()
        {
            Vector3 p = target.position + offset;
            if (cam != null && lookAhead > 0f)
            {
                Vector3 f = cam.forward;
                f.y = 0f;
                if (f.sqrMagnitude > 0.0001f) p += f.normalized * lookAhead;
            }
            return p;
        }

        // 순간이동(불러오기, 빠른 이동) 뒤에 바로 옮긴다
        public void Snap()
        {
            if (target != null) transform.position = Desired();
        }

        void ApplyScale()
        {
            appliedScale = emissionScale;
            if (systems == null) return;
            for (int i = 0; i < systems.Length; i++)
            {
                var em = systems[i].emission;
                em.rateOverTimeMultiplier = baseRates[i] * emissionScale;
            }
        }
    }
}
