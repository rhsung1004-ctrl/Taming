using UnityEngine;

namespace Necro
{
    // 3인칭 궤도 카메라: 부드러운 추적, 회전, 줌, 벽 충돌 시 앞으로 당김.
    // 비행·탑승 연출이 들어가는 3단계에서 Cinemachine으로 확장 예정.
    public class OrbitCamera : MonoBehaviour
    {
        [Header("대상")]
        [Tooltip("따라갈 대상 (주인공)")] public Transform target;
        [Tooltip("카메라 회전·줌 입력을 읽을 곳")] public PlayerInputReader input;
        [Tooltip("대상 발밑에서 카메라가 바라보는 점까지의 높이 (m)")] public Vector3 pivotOffset = new Vector3(0f, 1.45f, 0f);

        [Header("거리·각도")]
        [Tooltip("카메라와 주인공 사이 거리 (m). 마우스 휠로 바뀐다")] public float distance = 5f;
        [Tooltip("휠로 당길 수 있는 가장 가까운 거리 (m)")] public float minDistance = 2f;
        [Tooltip("휠로 밀 수 있는 가장 먼 거리 (m)")] public float maxDistance = 9f;
        [Tooltip("좌우 각도 (도). 시작할 때 대상이 보는 방향으로 맞춘다")] public float yaw;
        [Tooltip("위아래 각도 (도). 클수록 위에서 내려다본다")] public float pitch = 12f;
        [Tooltip("올려다볼 수 있는 한계 (도, 음수 = 아래에서 위로)")] public float minPitch = -35f;
        [Tooltip("내려다볼 수 있는 한계 (도)")] public float maxPitch = 70f;

        [Header("부드러움")]
        [Tooltip("주인공을 따라가는 빠르기 (클수록 바로 붙는다)")] public float followSharpness = 14f;
        [Tooltip("벽에서 벗어날 때 원래 거리로 돌아가는 빠르기")] public float zoomSharpness = 8f;

        [Header("충돌")]
        [Tooltip("벽 충돌 검사 공의 반지름 (m). 카메라가 벽에 파고들면 키운다")] public float collisionRadius = 0.25f;
        [Tooltip("카메라를 앞으로 당기는 충돌 층")] public LayerMask collisionMask = ~(1 << 2);

        float currentDistance;
        Vector3 smoothedPivot;
        readonly RaycastHit[] hits = new RaycastHit[16];

        void Start()
        {
            currentDistance = distance;
            if (target != null)
            {
                smoothedPivot = target.position + pivotOffset;
                yaw = target.eulerAngles.y;
            }
        }

        void LateUpdate()
        {
            if (target == null) return;
            float dt = Time.deltaTime;

            if (input != null)
            {
                yaw += input.Look.x;
                pitch = Mathf.Clamp(pitch - input.Look.y, minPitch, maxPitch);
                distance = Mathf.Clamp(distance - input.Zoom * 0.8f, minDistance, maxDistance);
            }

            Vector3 pivot = target.position + pivotOffset;
            smoothedPivot = Vector3.Lerp(smoothedPivot, pivot, 1f - Mathf.Exp(-followSharpness * dt));
            Quaternion rot = Quaternion.Euler(pitch, yaw, 0f);
            Vector3 back = rot * Vector3.back;

            float wanted = distance;
            int n = Physics.SphereCastNonAlloc(smoothedPivot, collisionRadius, back, hits, distance, collisionMask, QueryTriggerInteraction.Ignore);
            for (int i = 0; i < n; i++)
            {
                var h = hits[i];
                if (h.collider.transform.IsChildOf(target)) continue;   // 주인공 자신은 무시
                if (h.distance <= 0f) continue;
                wanted = Mathf.Min(wanted, Mathf.Max(minDistance * 0.4f, h.distance - 0.1f));
            }
            // 벽에 막힐 때는 즉시 당기고, 풀릴 때는 부드럽게 멀어진다
            currentDistance = wanted < currentDistance ? wanted : Mathf.Lerp(currentDistance, wanted, 1f - Mathf.Exp(-zoomSharpness * dt));

            transform.position = smoothedPivot + back * currentDistance;
            transform.rotation = rot;
        }
    }
}
