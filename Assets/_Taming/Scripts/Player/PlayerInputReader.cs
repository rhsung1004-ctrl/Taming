using UnityEngine;
using UnityEngine.InputSystem;

namespace Taming
{
    // 입력을 한 곳에서 읽는다. 키보드·마우스·게임패드 지원.
    // 모바일 터치는 Input System의 On-Screen Stick/Button이 게임패드 입력을 흉내 내므로 그대로 동작한다.
    public class PlayerInputReader : MonoBehaviour
    {
        public Vector2 Move { get; private set; }
        public Vector2 Look { get; private set; }      // 이번 프레임 카메라 회전량 (도 단위)
        public float Zoom { get; private set; }
        public bool JumpPressed { get; private set; }
        public bool JumpHeld { get; private set; }
        public bool Sprint { get; private set; }

        [Tooltip("마우스 감도 (픽셀당 도)")] public float mouseSensitivity = 0.15f;
        [Tooltip("스틱 감도 (초당 도)")] public float stickSensitivity = 160f;

        InputAction move, lookMouse, lookStick, zoom, jump, sprint;

        void Awake()
        {
            move = new InputAction("Move", InputActionType.Value);
            move.AddCompositeBinding("2DVector")
                .With("Up", "<Keyboard>/w").With("Down", "<Keyboard>/s")
                .With("Left", "<Keyboard>/a").With("Right", "<Keyboard>/d");
            move.AddCompositeBinding("2DVector")
                .With("Up", "<Keyboard>/upArrow").With("Down", "<Keyboard>/downArrow")
                .With("Left", "<Keyboard>/leftArrow").With("Right", "<Keyboard>/rightArrow");
            move.AddBinding("<Gamepad>/leftStick");

            lookMouse = new InputAction("LookMouse", InputActionType.Value, "<Mouse>/delta");
            lookStick = new InputAction("LookStick", InputActionType.Value, "<Gamepad>/rightStick");
            zoom = new InputAction("Zoom", InputActionType.Value, "<Mouse>/scroll/y");

            jump = new InputAction("Jump", InputActionType.Button);
            jump.AddBinding("<Keyboard>/space");
            jump.AddBinding("<Gamepad>/buttonSouth");

            sprint = new InputAction("Sprint", InputActionType.Button);
            sprint.AddBinding("<Keyboard>/leftShift");
            sprint.AddBinding("<Gamepad>/leftStickPress");
        }

        void OnEnable()
        {
            move.Enable(); lookMouse.Enable(); lookStick.Enable(); zoom.Enable(); jump.Enable(); sprint.Enable();
        }

        void OnDisable()
        {
            move.Disable(); lookMouse.Disable(); lookStick.Disable(); zoom.Disable(); jump.Disable(); sprint.Disable();
        }

        void OnDestroy()
        {
            move.Dispose(); lookMouse.Dispose(); lookStick.Dispose(); zoom.Dispose(); jump.Dispose(); sprint.Dispose();
        }

        void Update()
        {
            Move = Vector2.ClampMagnitude(move.ReadValue<Vector2>(), 1f);

            // PC에서는 마우스 오른쪽 버튼을 누른 채 움직일 때만 카메라 회전
            Vector2 look = Vector2.zero;
            var mouse = Mouse.current;
            if (mouse != null && mouse.rightButton.isPressed) look += lookMouse.ReadValue<Vector2>() * mouseSensitivity;
            look += lookStick.ReadValue<Vector2>() * stickSensitivity * Time.deltaTime;
            Look = look;

            Zoom = zoom.ReadValue<float>() / 120f;
            JumpPressed = jump.WasPressedThisFrame();
            JumpHeld = jump.IsPressed();
            Sprint = sprint.IsPressed();
        }
    }
}
