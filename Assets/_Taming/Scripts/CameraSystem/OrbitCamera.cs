using UnityEngine;

namespace Taming
{
    // 3인칭 궤도 카메라: 부드러운 추적, 회전, 줌, 벽 충돌 시 앞으로 당김.
    // 비행·탑승 연출이 들어가는 3단계에서 Cinemachine으로 확장 예정.
    public class OrbitCamera : MonoBehaviour
    {
        [Header("대상")]
        public Transform target;
        public PlayerInputReader input;
        public Vector3 pivotOffset = new Vector3(0f, 1.45f, 0f);

        [Header("거리·각도")]
        public float distance = 5f;
        public float minDistance = 2f;
        public float maxDistance = 9f;
        public float yaw;
        public float pitch = 12f;
        public float minPitch = -35f;
        public float maxPitch = 70f;

        [Header("부드러움")]
        public float followSharpness = 14f;
        public float zoomSharpness = 8f;

        [Header("충돌")]
        public float collisionRadius = 0.25f;
        public LayerMask collisionMask = ~(1 << 2);

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
