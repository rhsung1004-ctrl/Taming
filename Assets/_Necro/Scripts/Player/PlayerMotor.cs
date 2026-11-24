using UnityEngine;

namespace Necro
{
    // 주인공 3인칭 이동: 가속/감속, 카메라 기준 방향, 코요테 타임, 점프 버퍼, 빠른 낙하.
    // 조작감이 퀄리티의 큰 부분이라 수치는 전부 Inspector에서 조정 가능하게 열어 둔다.
    [RequireComponent(typeof(CharacterController))]
    public class PlayerMotor : MonoBehaviour
    {
        [Header("참조")]
        [Tooltip("이동·점프 입력을 읽을 곳 (비우면 같은 오브젝트에서 찾는다)")] public PlayerInputReader input;
        [Tooltip("이동 방향의 기준 카메라 (비우면 Main Camera)")] public Transform cameraTransform;

        [Header("이동 속도 (m/s)")]
        [Tooltip("스틱을 절반쯤 밀 때 걷는 속도 (m/s)")] public float walkSpeed = 2.4f;
        [Tooltip("키보드 이동·스틱을 끝까지 밀 때 달리는 속도 (m/s)")] public float runSpeed = 5.6f;
        [Tooltip("Shift·왼쪽 스틱 누르기로 질주할 때 속도 (m/s)")] public float sprintSpeed = 8.5f;
        [Tooltip("빨라질 때 초당 늘어나는 속도 (m/s²). 클수록 바로 최고 속도")] public float acceleration = 22f;
        [Tooltip("느려질 때 초당 줄어드는 속도 (m/s²). 클수록 바로 멈춘다")] public float deceleration = 28f;
        [Tooltip("공중에서 방향을 바꾸는 힘 (땅 위 대비 비율)")] [Range(0f, 1f)] public float airControl = 0.35f;
        [Tooltip("몸을 돌리는 빠르기 (초당 도)")] public float turnSpeed = 720f;

        [Header("점프")]
        [Tooltip("점프 키를 끝까지 누를 때 오르는 높이 (m)")] public float jumpHeight = 1.3f;
        [Tooltip("중력 (m/s², 음수). 클수록 점프가 짧고 묵직하다")] public float gravity = -22f;
        [Tooltip("떨어질 때 중력 배율 (클수록 빨리 떨어진다)")] public float fallMultiplier = 1.7f;
        [Tooltip("발판에서 벗어난 뒤에도 점프를 받아 주는 시간 (초)")] public float coyoteTime = 0.12f;
        [Tooltip("땅에 닿기 직전에 누른 점프를 기억하는 시간 (초)")] public float jumpBufferTime = 0.15f;

        CharacterController cc;
        Vector3 planarVelocity;
        float verticalVelocity;
        float lastGroundedTime = -10f;
        float lastJumpPressTime = -10f;

        public Vector3 PlanarVelocity { get { return planarVelocity; } }
        public float PlanarSpeed { get { return planarVelocity.magnitude; } }
        public float VerticalSpeed { get { return verticalVelocity; } }
        public bool Grounded { get; private set; }
        public bool JumpedThisFrame { get; private set; }

        void Awake()
        {
            cc = GetComponent<CharacterController>();
            if (input == null) input = GetComponent<PlayerInputReader>();
        }

        void Start()
        {
            if (cameraTransform == null && Camera.main != null) cameraTransform = Camera.main.transform;
        }

        void Update()
        {
            float dt = Time.deltaTime;
            JumpedThisFrame = false;
            Vector2 m = input != null ? input.Move : Vector2.zero;
            float mag = Mathf.Clamp01(m.magnitude);

            // 카메라 기준 이동 방향
            Vector3 fwd = Vector3.forward, right = Vector3.right;
            if (cameraTransform != null)
            {
                fwd = Vector3.ProjectOnPlane(cameraTransform.forward, Vector3.up).normalized;
                right = Vector3.ProjectOnPlane(cameraTransform.right, Vector3.up).normalized;
            }
            Vector3 wish = fwd * m.y + right * m.x;
            if (wish.sqrMagnitude > 1e-4f) wish.Normalize();

            // 스틱을 살짝 밀면 걷기, 끝까지 밀면 달리기, 스프린트 키로 질주
            float speed;
            if (input != null && input.Sprint && mag > 0.1f) speed = sprintSpeed;
            else if (mag < 0.5f) speed = walkSpeed * (mag / 0.5f);
            else speed = Mathf.Lerp(walkSpeed, runSpeed, (mag - 0.5f) / 0.5f);

            Vector3 target = wish * speed;
            float rate = target.sqrMagnitude > planarVelocity.sqrMagnitude ? acceleration : deceleration;
            if (!Grounded) rate *= airControl;
            planarVelocity = Vector3.MoveTowards(planarVelocity, target, rate * dt);

            if (planarVelocity.sqrMagnitude > 0.01f)
            {
                Quaternion look = Quaternion.LookRotation(planarVelocity.normalized, Vector3.up);
                transform.rotation = Quaternion.RotateTowards(transform.rotation, look, turnSpeed * dt);
            }

            // 점프
            if (Grounded) lastGroundedTime = Time.time;
            if (input != null && input.JumpPressed) lastJumpPressTime = Time.time;
            bool canJump = Time.time - lastGroundedTime <= coyoteTime;
            bool wantsJump = Time.time - lastJumpPressTime <= jumpBufferTime;
            if (canJump && wantsJump)
            {
                verticalVelocity = Mathf.Sqrt(2f * jumpHeight * -gravity);
                lastGroundedTime = -10f;
                lastJumpPressTime = -10f;
                JumpedThisFrame = true;
            }
            else if (Grounded && verticalVelocity < 0f)
            {
                verticalVelocity = -2f;   // 경사면에 붙어 있게
            }

            float g = gravity;
            if (verticalVelocity < 0f) g *= fallMultiplier;
            else if (input != null && !input.JumpHeld) g *= 1.4f;   // 점프 키를 짧게 누르면 낮게 뜀
            verticalVelocity += g * dt;

            cc.Move((planarVelocity + Vector3.up * verticalVelocity) * dt);
            Grounded = cc.isGrounded;
        }

        public void Teleport(Vector3 position)
        {
            cc.enabled = false;
            transform.position = position;
            cc.enabled = true;
            planarVelocity = Vector3.zero;
            verticalVelocity = 0f;
        }
    }
}
