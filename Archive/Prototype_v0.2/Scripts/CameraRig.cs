using UnityEngine;

// 3인칭 백뷰 카메라. 화면 오른쪽을 드래그하면 회전, 휠로 줌(에디터).
public class CameraRig : MonoBehaviour
{
    public PlayerController target;
    public float yaw, pitch = 15f;
    float dist = 7f, zoom;
    const int Mask = ~(1 << 2);

    void LateUpdate()
    {
        if (target == null || GameHUD.I == null) return;
        Vector2 d = GameHUD.I.CamDelta;
        yaw += d.x * 0.28f;
        pitch = Mathf.Clamp(pitch + d.y * 0.22f, -25f, 70f);
        zoom = Mathf.Clamp(zoom - TouchInput.Scroll * 1.2f, -3f, 8f);

        float want = 7f + zoom + (target.Flying ? 4f : target.Riding ? 1.5f : 0f);
        dist = Mathf.Lerp(dist, want, Time.deltaTime * 3f);

        Vector3 pivot = target.transform.position + Vector3.up * (1.6f + target.rig.seat);
        Quaternion rot = Quaternion.Euler(pitch, yaw, 0f);
        Vector3 back = rot * Vector3.back;
        float d2 = dist;
        RaycastHit hit;
        if (Physics.SphereCast(pivot, 0.3f, back, out hit, dist, Mask, QueryTriggerInteraction.Ignore))
            d2 = Mathf.Max(0.8f, hit.distance - 0.1f);
        transform.position = pivot + back * d2;
        transform.rotation = rot;
    }
}
