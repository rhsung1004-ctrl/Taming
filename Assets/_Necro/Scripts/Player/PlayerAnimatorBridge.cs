using System.Collections.Generic;
using UnityEngine;

namespace Necro
{
    // PlayerMotor 상태를 Animator 파라미터로 넘긴다.
    // 파라미터: Speed(float), Grounded(bool), VerticalSpeed(float), Jump(trigger)
    // "Tools → Necro → 플레이어 애니메이터 만들기"로 만든 컨트롤러와 짝이 맞는다.
    public class PlayerAnimatorBridge : MonoBehaviour
    {
        [Header("참조")]
        [Tooltip("속도·착지 상태를 읽을 이동 컴포넌트 (비우면 같은 오브젝트에서 찾는다)")] public PlayerMotor motor;
        [Tooltip("파라미터를 넘길 Animator (비우면 자식에서 찾는다)")] public Animator animator;
        [Header("부드러움")]
        [Tooltip("속도 변화를 부드럽게 (클수록 빠르게 따라감)")] public float speedDamp = 10f;

        static readonly int SpeedId = Animator.StringToHash("Speed");
        static readonly int GroundedId = Animator.StringToHash("Grounded");
        static readonly int VerticalId = Animator.StringToHash("VerticalSpeed");
        static readonly int JumpId = Animator.StringToHash("Jump");

        readonly HashSet<int> available = new HashSet<int>();
        float speed;

        void Awake()
        {
            if (motor == null) motor = GetComponent<PlayerMotor>();
            if (animator == null) animator = GetComponentInChildren<Animator>();
            Cache();
        }

        void Cache()
        {
            available.Clear();
            if (animator == null || animator.runtimeAnimatorController == null) return;
            animator.applyRootMotion = false;
            foreach (var p in animator.parameters) available.Add(p.nameHash);
        }

        void Update()
        {
            if (animator == null || motor == null) return;
            if (available.Count == 0) { Cache(); if (available.Count == 0) return; }

            speed = Mathf.Lerp(speed, motor.PlanarSpeed, 1f - Mathf.Exp(-speedDamp * Time.deltaTime));
            if (available.Contains(SpeedId)) animator.SetFloat(SpeedId, speed);
            if (available.Contains(GroundedId)) animator.SetBool(GroundedId, motor.Grounded);
            if (available.Contains(VerticalId)) animator.SetFloat(VerticalId, motor.VerticalSpeed);
            if (motor.JumpedThisFrame && available.Contains(JumpId)) animator.SetTrigger(JumpId);
        }
    }
}
