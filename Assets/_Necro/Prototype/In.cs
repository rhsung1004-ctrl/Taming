using UnityEngine;
using UnityEngine.InputSystem;

namespace Necro.Proto
{
    // 프로토타입 입력: 키보드·마우스 + 게임패드. 매 프레임 한 번 읽어 정적 값으로 둔다.
    [DefaultExecutionOrder(-200)]
    public class In : MonoBehaviour
    {
        public static Vector2 Move, Look;
        public static float Scroll;
        public static bool AttackHeld, SpearDown, RaiseDown, RaiseHeld, BlastDown, BuffDown, CommandDown;
        public static bool DashDown, MountDown, JumpDown, JumpHeld, DescendHeld, PauseDown, ClickDown;
        public static bool CrownDown, DescentDown, RosterDown, EscDown, DebugTierDown, PointDown, CrownNextDown, LookDown;

        const float MouseSens = 0.12f;    // 픽셀당 도
        const float StickSens = 170f;     // 초당 도

        public static bool CursorLocked { get { return Cursor.lockState == CursorLockMode.Locked; } }

        public static void LockCursor(bool on)
        {
            Cursor.lockState = on ? CursorLockMode.Locked : CursorLockMode.None;
            Cursor.visible = !on;
        }

        void Update()
        {
            Move = Look = Vector2.zero;
            Scroll = 0f;
            AttackHeld = SpearDown = RaiseDown = RaiseHeld = BlastDown = BuffDown = CommandDown = false;
            DashDown = MountDown = JumpDown = JumpHeld = DescendHeld = PauseDown = ClickDown = false;
            CrownDown = DescentDown = RosterDown = EscDown = DebugTierDown = PointDown = CrownNextDown = LookDown = false;

            var k = Keyboard.current;
            if (k != null)
            {
                float x = 0f, y = 0f;
                if (k.aKey.isPressed || k.leftArrowKey.isPressed) x -= 1f;
                if (k.dKey.isPressed || k.rightArrowKey.isPressed) x += 1f;
                if (k.sKey.isPressed || k.downArrowKey.isPressed) y -= 1f;
                if (k.wKey.isPressed || k.upArrowKey.isPressed) y += 1f;
                Move = new Vector2(x, y);
                RaiseDown |= k.eKey.wasPressedThisFrame;
                RaiseHeld |= k.eKey.isPressed;
                BlastDown |= k.qKey.wasPressedThisFrame;
                BuffDown |= k.rKey.wasPressedThisFrame;
                CommandDown |= k.fKey.wasPressedThisFrame;
                DashDown |= k.leftShiftKey.wasPressedThisFrame;
                MountDown |= k.vKey.wasPressedThisFrame;
                JumpDown |= k.spaceKey.wasPressedThisFrame;
                JumpHeld |= k.spaceKey.isPressed;
                DescendHeld |= k.leftCtrlKey.isPressed || k.cKey.isPressed;
                PauseDown |= k.escapeKey.wasPressedThisFrame || k.pKey.wasPressedThisFrame;
                EscDown |= k.escapeKey.wasPressedThisFrame;
                CrownDown |= k.gKey.wasPressedThisFrame;
                DescentDown |= k.zKey.wasPressedThisFrame;
                RosterDown |= k.tabKey.wasPressedThisFrame;
                DebugTierDown |= k.f1Key.wasPressedThisFrame;
                LookDown |= k.f2Key.wasPressedThisFrame;
                CrownNextDown |= k.tKey.wasPressedThisFrame;
            }

            var m = Mouse.current;
            if (m != null)
            {
                ClickDown |= m.leftButton.wasPressedThisFrame;
                if (CursorLocked)
                {
                    Look += m.delta.ReadValue() * MouseSens;
                    AttackHeld |= m.leftButton.isPressed;
                    SpearDown |= m.rightButton.wasPressedThisFrame;
                    PointDown |= m.middleButton.wasPressedThisFrame;
                }
                Scroll = m.scroll.ReadValue().y / 120f;
            }

            var g = Gamepad.current;
            if (g != null)
            {
                Move += g.leftStick.ReadValue();
                Look += g.rightStick.ReadValue() * StickSens * Time.unscaledDeltaTime;
                AttackHeld |= g.rightTrigger.isPressed;
                SpearDown |= g.rightShoulder.wasPressedThisFrame;
                RaiseDown |= g.buttonWest.wasPressedThisFrame;
                RaiseHeld |= g.buttonWest.isPressed;
                BlastDown |= g.leftShoulder.wasPressedThisFrame;
                BuffDown |= g.buttonNorth.wasPressedThisFrame;
                CommandDown |= g.dpad.left.wasPressedThisFrame;
                DashDown |= g.buttonEast.wasPressedThisFrame;
                MountDown |= g.dpad.up.wasPressedThisFrame;
                JumpDown |= g.buttonSouth.wasPressedThisFrame;
                JumpHeld |= g.buttonSouth.isPressed;
                DescendHeld |= g.leftTrigger.isPressed;
                PauseDown |= g.startButton.wasPressedThisFrame;
                CrownDown |= g.dpad.right.wasPressedThisFrame;
                DescentDown |= g.dpad.down.wasPressedThisFrame;
                RosterDown |= g.selectButton.wasPressedThisFrame;
                PointDown |= g.leftStickButton.wasPressedThisFrame;
                CrownNextDown |= g.rightStickButton.wasPressedThisFrame;
            }
            Move = Vector2.ClampMagnitude(Move, 1f);
        }
    }
}
