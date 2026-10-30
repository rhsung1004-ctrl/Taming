using System.Collections.Generic;
using UnityEngine;
#if !ENABLE_LEGACY_INPUT_MANAGER && ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
#endif

public struct PointerInfo
{
    public int id;
    public Vector2 pos;   // 화면 좌표 (왼쪽 아래가 원점)
    public bool began;
    public bool ended;
}

// 터치·마우스·키보드 입력을 한 곳에서 읽는다.
// 구 Input Manager / 새 Input System 어느 쪽 설정이든 그대로 동작.
[DefaultExecutionOrder(-200)]
public class TouchInput : MonoBehaviour
{
    public static readonly List<PointerInfo> Pointers = new List<PointerInfo>();
    public static Vector2 KeyMove;
    public static bool JumpHeld, JumpDown, DescendHeld, AttackDown, RideDown, TameDown, FeedDown, TargetDown, BondDown;
    public static float Scroll;

    void Update()
    {
        Pointers.Clear();
        KeyMove = Vector2.zero;
        JumpHeld = JumpDown = DescendHeld = AttackDown = RideDown = TameDown = FeedDown = TargetDown = BondDown = false;
        Scroll = 0f;
#if ENABLE_LEGACY_INPUT_MANAGER
        ReadLegacy();
#elif ENABLE_INPUT_SYSTEM
        ReadNew();
#endif
    }

#if ENABLE_LEGACY_INPUT_MANAGER
    void ReadLegacy()
    {
        if (Input.touchSupported)
        {
            for (int i = 0; i < Input.touchCount; i++)
            {
                Touch t = Input.GetTouch(i);
                Pointers.Add(new PointerInfo
                {
                    id = t.fingerId,
                    pos = t.position,
                    began = t.phase == TouchPhase.Began,
                    ended = t.phase == TouchPhase.Ended || t.phase == TouchPhase.Canceled
                });
            }
        }
        else if (Input.GetMouseButton(0) || Input.GetMouseButtonUp(0))
        {
            Pointers.Add(new PointerInfo
            {
                id = -1,
                pos = Input.mousePosition,
                began = Input.GetMouseButtonDown(0),
                ended = Input.GetMouseButtonUp(0)
            });
        }

        float x = 0f, y = 0f;
        if (Input.GetKey(KeyCode.A) || Input.GetKey(KeyCode.LeftArrow)) x -= 1f;
        if (Input.GetKey(KeyCode.D) || Input.GetKey(KeyCode.RightArrow)) x += 1f;
        if (Input.GetKey(KeyCode.S) || Input.GetKey(KeyCode.DownArrow)) y -= 1f;
        if (Input.GetKey(KeyCode.W) || Input.GetKey(KeyCode.UpArrow)) y += 1f;
        KeyMove = new Vector2(x, y);
        JumpHeld = Input.GetKey(KeyCode.Space);
        JumpDown = Input.GetKeyDown(KeyCode.Space);
        DescendHeld = Input.GetKey(KeyCode.LeftShift);
        AttackDown = Input.GetKeyDown(KeyCode.F);
        RideDown = Input.GetKeyDown(KeyCode.R);
        TameDown = Input.GetKeyDown(KeyCode.T);
        FeedDown = Input.GetKeyDown(KeyCode.E);
        TargetDown = Input.GetKeyDown(KeyCode.Tab);
        BondDown = Input.GetKeyDown(KeyCode.Space) || Input.GetKeyDown(KeyCode.B);
        Scroll = Input.mouseScrollDelta.y;
    }
#endif

#if !ENABLE_LEGACY_INPUT_MANAGER && ENABLE_INPUT_SYSTEM
    void ReadNew()
    {
        var ts = Touchscreen.current;
        if (ts != null)
        {
            foreach (var t in ts.touches)
            {
                bool pressed = t.press.isPressed;
                bool released = t.press.wasReleasedThisFrame;
                if (!pressed && !released) continue;
                Pointers.Add(new PointerInfo
                {
                    id = t.touchId.ReadValue(),
                    pos = t.position.ReadValue(),
                    began = t.press.wasPressedThisFrame,
                    ended = released
                });
            }
        }
        else if (Mouse.current != null)
        {
            var m = Mouse.current;
            if (m.leftButton.isPressed || m.leftButton.wasReleasedThisFrame)
            {
                Pointers.Add(new PointerInfo
                {
                    id = -1,
                    pos = m.position.ReadValue(),
                    began = m.leftButton.wasPressedThisFrame,
                    ended = m.leftButton.wasReleasedThisFrame
                });
            }
            Scroll = m.scroll.ReadValue().y / 120f;
        }

        var k = Keyboard.current;
        if (k == null) return;
        float x = 0f, y = 0f;
        if (k.aKey.isPressed || k.leftArrowKey.isPressed) x -= 1f;
        if (k.dKey.isPressed || k.rightArrowKey.isPressed) x += 1f;
        if (k.sKey.isPressed || k.downArrowKey.isPressed) y -= 1f;
        if (k.wKey.isPressed || k.upArrowKey.isPressed) y += 1f;
        KeyMove = new Vector2(x, y);
        JumpHeld = k.spaceKey.isPressed;
        JumpDown = k.spaceKey.wasPressedThisFrame;
        DescendHeld = k.leftShiftKey.isPressed;
        AttackDown = k.fKey.wasPressedThisFrame;
        RideDown = k.rKey.wasPressedThisFrame;
        TameDown = k.tKey.wasPressedThisFrame;
        FeedDown = k.eKey.wasPressedThisFrame;
        TargetDown = k.tabKey.wasPressedThisFrame;
        BondDown = k.spaceKey.wasPressedThisFrame || k.bKey.wasPressedThisFrame;
    }
#endif
}
