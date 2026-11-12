using UnityEngine;

namespace Necro.Proto
{
    // 3인칭 카메라. 마우스로 돌리고 휠로 당긴다.
    public class OrbitCam : MonoBehaviour
    {
        public PlayerCtl target;
        public float yaw, pitch = 14f;
        float dist = 6.5f, zoom;
        const int Mask = ~(1 << 2);
        static float shake;

        // 큰 기술의 타격감: 0.2(가벼움) ~ 1(금주·왕관 스킬)
        public static void Shake(float amount) { shake = Mathf.Max(shake, amount); }

        void LateUpdate()
        {
            if (target == null) return;
            if (!Game.I.paused)
            {
                yaw += In.Look.x;
                pitch = Mathf.Clamp(pitch - In.Look.y, -40f, 78f);
                zoom = Mathf.Clamp(zoom - In.Scroll * 1.2f, -3f, 10f);
            }
            float want = 6.5f + zoom + (target.Riding ? 12f : 0f);
            dist = Mathf.Lerp(dist, want, Time.unscaledDeltaTime * 3f);

            Quaternion rot = Quaternion.Euler(pitch, yaw, 0f);
            // 어깨 너머로 보도록 살짝 오른쪽에서 본다 (탑승 중에는 정중앙)
            Vector3 pivot = target.transform.position + Vector3.up * (1.65f + target.rig.seat * 0.9f) + rot * Vector3.right * (target.Riding ? 0f : 0.55f);
            Vector3 back = rot * Vector3.back;
            float d2 = dist;
            RaycastHit hit;
            if (Physics.SphereCast(pivot, 0.3f, back, out hit, dist, Mask, QueryTriggerInteraction.Ignore))
                d2 = Mathf.Max(0.8f, hit.distance - 0.1f);
            shake = Mathf.MoveTowards(shake, 0f, Time.unscaledDeltaTime * 1.8f);
            transform.position = pivot + back * d2 + (shake > 0.001f ? Random.insideUnitSphere * shake * 0.35f : Vector3.zero);
            transform.rotation = rot;
        }
    }
}
