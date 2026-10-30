using System.Collections.Generic;
using UnityEngine;

// 몬스터 몸체 애니메이션 (다리 흔들기, 날갯짓, 꼬리, 슬라임 출렁임, 공격 돌진)
public class BodyRig
{
    public BodyShape shape;
    public Transform root;
    public Transform main;
    public Vector3 mainBaseScale;
    public readonly List<Transform> legs = new List<Transform>();
    public readonly List<float> legPhase = new List<float>();
    public Transform wingL, wingR, tail;
    public float lunge;
    public ModelAnimator anim;     // 실제 모델을 쓸 때만
    public bool usesModel;

    public void OnAttack()
    {
        if (anim != null) anim.Attack();
        else lunge = 1f;
    }

    public void Animate(float move01, bool flying, float dt)
    {
        float t = Time.time;
        if (usesModel)
        {
            if (anim != null) anim.SetState(move01, flying, false);
            lunge = Mathf.MoveTowards(lunge, 0f, dt * 4f);
            if (root != null) root.localPosition = new Vector3(0f, flying ? Mathf.Sin(t * 3f) * 0.15f : 0f, Mathf.Sin(lunge * Mathf.PI) * 0.5f);
            return;
        }
        for (int i = 0; i < legs.Count; i++)
        {
            float a = flying ? 25f : Mathf.Sin(t * 11f + legPhase[i]) * 35f * move01;
            legs[i].localRotation = Quaternion.Euler(a, 0f, 0f);
        }
        if (wingL != null)
        {
            float flap = flying
                ? Mathf.Sin(t * 9f) * 45f
                : 8f + Mathf.Sin(t * 2f) * 4f + move01 * Mathf.Sin(t * 14f) * 15f;
            wingL.localRotation = Quaternion.Euler(0f, 0f, flap);
            wingR.localRotation = Quaternion.Euler(0f, 0f, -flap);
        }
        if (tail != null)
            tail.localRotation = Quaternion.Euler(0f, Mathf.Sin(t * 4f) * (15f + 20f * move01), 0f);

        if (shape == BodyShape.Slime && main != null)
        {
            float s = Mathf.Sin(t * 6f) * (0.05f + 0.08f * move01);
            main.localScale = new Vector3(mainBaseScale.x * (1f - s), mainBaseScale.y * (1f + s), mainBaseScale.z * (1f - s));
        }

        lunge = Mathf.MoveTowards(lunge, 0f, dt * 4f);
        if (root != null)
            root.localPosition = new Vector3(0f, flying ? Mathf.Sin(t * 3f) * 0.15f : 0f, Mathf.Sin(lunge * Mathf.PI) * 0.5f);
    }
}

// 주인공(여성 테이머) 애니메이션
public class TamerRig
{
    public Transform model, legL, legR, armL, armR, ponytail, staffTip;
    public float seat;   // 탈것에 탔을 때 모델을 올리는 높이
    public ModelAnimator anim;
    public bool usesModel;

    public void OnAttack()
    {
        if (anim != null) anim.Attack();
    }

    public void Animate(float move, bool riding, bool airborne, float attack)
    {
        float t = Time.time;
        if (usesModel)
        {
            if (anim != null) anim.SetState(move, airborne, riding);
            model.localPosition = new Vector3(0f, seat, 0f);
            return;
        }
        float bob = 0f;
        if (riding)
        {
            legL.localRotation = Quaternion.Euler(-75f, 0f, -25f);
            legR.localRotation = Quaternion.Euler(-75f, 0f, 25f);
            armL.localRotation = Quaternion.Euler(-35f, 0f, -12f);
            armR.localRotation = Quaternion.Euler(-35f, 0f, 12f);
        }
        else if (airborne)
        {
            legL.localRotation = Quaternion.Euler(-20f, 0f, 0f);
            legR.localRotation = Quaternion.Euler(10f, 0f, 0f);
            armL.localRotation = Quaternion.Euler(0f, 0f, -35f);
            armR.localRotation = Quaternion.Euler(0f, 0f, 35f);
        }
        else
        {
            float a = Mathf.Sin(t * 10f) * 38f * move;
            legL.localRotation = Quaternion.Euler(a, 0f, 0f);
            legR.localRotation = Quaternion.Euler(-a, 0f, 0f);
            armL.localRotation = Quaternion.Euler(-a * 0.7f, 0f, -6f);
            armR.localRotation = Quaternion.Euler(a * 0.7f, 0f, 6f);
            bob = Mathf.Abs(Mathf.Sin(t * 10f)) * 0.06f * move;
        }
        if (attack > 0f) armR.localRotation = Quaternion.Euler(-110f * attack, 0f, 8f);
        ponytail.localRotation = Quaternion.Euler(Mathf.Sin(t * 5f) * 6f + move * 18f, Mathf.Sin(t * 3f) * 6f, 0f);
        model.localPosition = new Vector3(0f, seat + bob, 0f);
    }
}

// 에셋 없이 기본 도형으로 캐릭터를 조립한다. 나중에 실제 3D 모델로 교체할 자리.
public static class Body
{
    static readonly Color Black = new Color(0.07f, 0.07f, 0.1f);
    const PrimitiveType S = PrimitiveType.Sphere;
    const PrimitiveType Cu = PrimitiveType.Cube;
    const PrimitiveType Cy = PrimitiveType.Cylinder;
    const PrimitiveType Ca = PrimitiveType.Capsule;

    static Transform P(PrimitiveType t, Transform parent, float x, float y, float z, float sx, float sy, float sz, Color c,
                       float rx = 0f, float ry = 0f, float rz = 0f, bool glow = false)
    {
        return Util.Part(t, parent, new Vector3(x, y, z), new Vector3(sx, sy, sz), c, new Vector3(rx, ry, rz), glow);
    }

    static Color Shade(Color c, float k) { return new Color(c.r * k, c.g * k, c.b * k, 1f); }

    public static float SeatHeight(BodyShape s)
    {
        switch (s)
        {
            case BodyShape.Quadruped: return 0.9f;
            case BodyShape.Bird: return 0.95f;
            case BodyShape.Lizard: return 0.65f;
            default: return 0.8f;
        }
    }

    static float ModelHeight(BodyShape s)
    {
        switch (s)
        {
            case BodyShape.Slime: return 0.85f;
            case BodyShape.Lizard: return 0.9f;
            default: return 1.25f;
        }
    }

    public static BodyRig Build(SpeciesDef d, Transform parent, float scale)
    {
        var rig = new BodyRig { shape = d.shape };
        var root = new GameObject("Body").transform;
        root.SetParent(parent, false);
        root.localScale = Vector3.one * scale;
        rig.root = root;

        var entry = ModelLibrary.Find(d.id);
        if (entry != null)
        {
            var mdl = ModelLibrary.Spawn(entry.prefab, root, ModelHeight(d.shape) * entry.heightMul, entry.yaw);
            rig.anim = ModelAnimator.Setup(mdl, entry.clips);
            rig.usesModel = true;
            return rig;
        }

        Color c = d.color;
        Color dark = Shade(c, 0.72f);
        Color light = Color.Lerp(c, Color.white, 0.45f);
        Color orange = new Color(1f, 0.7f, 0.2f);

        switch (d.shape)
        {
            case BodyShape.Slime:
            {
                rig.main = P(S, root, 0f, 0.42f, 0f, 1f, 0.82f, 1f, c);
                rig.mainBaseScale = rig.main.localScale;
                P(S, rig.main, -0.17f, 0.12f, 0.45f, 0.13f, 0.16f, 0.1f, Black);
                P(S, rig.main, 0.17f, 0.12f, 0.45f, 0.13f, 0.16f, 0.1f, Black);
                P(S, rig.main, -0.22f, 0.3f, 0.3f, 0.12f, 0.1f, 0.08f, Color.white);
                P(Cu, rig.main, 0f, -0.02f, 0.49f, 0.12f, 0.03f, 0.02f, Black);
                break;
            }
            case BodyShape.Quadruped:
            {
                rig.main = P(Ca, root, 0f, 0.65f, 0f, 0.5f, 0.55f, 0.5f, c, 90f);
                P(S, root, 0f, 0.98f, 0.55f, 0.46f, 0.46f, 0.46f, c);
                P(Cu, root, 0f, 0.9f, 0.82f, 0.2f, 0.16f, 0.26f, light);
                P(S, root, 0f, 0.93f, 0.96f, 0.08f, 0.08f, 0.08f, Black);
                P(Cu, root, -0.13f, 1.22f, 0.5f, 0.1f, 0.22f, 0.08f, dark, 0f, 0f, 12f);
                P(Cu, root, 0.13f, 1.22f, 0.5f, 0.1f, 0.22f, 0.08f, dark, 0f, 0f, -12f);
                P(S, root, -0.11f, 1.03f, 0.75f, 0.08f, 0.08f, 0.08f, Black);
                P(S, root, 0.11f, 1.03f, 0.75f, 0.08f, 0.08f, 0.08f, Black);
                for (int i = 0; i < 4; i++)
                {
                    float sx = (i % 2 == 0) ? -0.16f : 0.16f;
                    float sz = (i < 2) ? 0.32f : -0.32f;
                    var leg = Util.Pivot(root, new Vector3(sx, 0.5f, sz));
                    P(Cy, leg, 0f, -0.25f, 0f, 0.13f, 0.25f, 0.13f, dark);
                    rig.legs.Add(leg);
                    rig.legPhase.Add(((i < 2) ? 0f : Mathf.PI) + ((i % 2 == 0) ? 0f : Mathf.PI));
                }
                rig.tail = Util.Pivot(root, new Vector3(0f, 0.75f, -0.5f));
                P(Ca, rig.tail, 0f, 0.12f, -0.25f, 0.16f, 0.28f, 0.16f, c, -55f);
                P(S, rig.tail, 0f, 0.3f, -0.46f, 0.15f, 0.15f, 0.15f, light);
                break;
            }
            case BodyShape.Bird:
            {
                bool griffon = d.id == "griffon";
                rig.main = P(S, root, 0f, 0.7f, 0f, 0.62f, 0.6f, 0.85f, c);
                P(S, root, 0f, 0.62f, 0.14f, 0.5f, 0.45f, 0.62f, light);
                P(S, root, 0f, 1.08f, 0.32f, 0.42f, 0.42f, 0.42f, griffon ? Color.white : c);
                P(Cu, root, 0f, 1.03f, 0.58f, 0.1f, 0.09f, 0.22f, orange);
                P(S, root, -0.12f, 1.13f, 0.48f, 0.07f, 0.07f, 0.07f, Black);
                P(S, root, 0.12f, 1.13f, 0.48f, 0.07f, 0.07f, 0.07f, Black);
                P(Cu, root, 0f, 1.33f, 0.25f, 0.05f, 0.18f, 0.14f, dark, -20f);
                rig.wingL = Util.Pivot(root, new Vector3(-0.28f, 0.82f, 0f));
                P(Cu, rig.wingL, -0.45f, 0f, -0.05f, 0.9f, 0.06f, 0.5f, dark);
                rig.wingR = Util.Pivot(root, new Vector3(0.28f, 0.82f, 0f));
                P(Cu, rig.wingR, 0.45f, 0f, -0.05f, 0.9f, 0.06f, 0.5f, dark);
                rig.tail = Util.Pivot(root, new Vector3(0f, 0.72f, -0.4f));
                P(Cu, rig.tail, 0f, 0f, -0.15f, 0.32f, 0.05f, 0.4f, dark, -20f);
                for (int i = 0; i < 2; i++)
                {
                    var leg = Util.Pivot(root, new Vector3(i == 0 ? -0.12f : 0.12f, 0.42f, 0.02f));
                    P(Cy, leg, 0f, -0.2f, 0f, 0.05f, 0.2f, 0.05f, orange);
                    rig.legs.Add(leg);
                    rig.legPhase.Add(i * Mathf.PI);
                }
                break;
            }
            case BodyShape.Lizard:
            {
                rig.main = P(Ca, root, 0f, 0.42f, 0f, 0.42f, 0.55f, 0.42f, c, 90f);
                P(S, root, 0f, 0.5f, 0.62f, 0.38f, 0.3f, 0.46f, c);
                P(S, root, -0.12f, 0.6f, 0.75f, 0.07f, 0.07f, 0.07f, Black);
                P(S, root, 0.12f, 0.6f, 0.75f, 0.07f, 0.07f, 0.07f, Black);
                for (int i = 0; i < 4; i++)
                    P(Cu, root, 0f, 0.66f, 0.3f - i * 0.22f, 0.06f, 0.14f, 0.1f, light, 45f);
                rig.tail = Util.Pivot(root, new Vector3(0f, 0.42f, -0.5f));
                P(Ca, rig.tail, 0f, 0f, -0.38f, 0.2f, 0.42f, 0.2f, dark, 90f);
                if (d.element == Element.Fire)
                    P(S, rig.tail, 0f, 0f, -0.82f, 0.2f, 0.2f, 0.2f, new Color(1f, 0.6f, 0.1f), 0f, 0f, 0f, true);
                for (int i = 0; i < 4; i++)
                {
                    float sx = (i % 2 == 0) ? -0.25f : 0.25f;
                    float sz = (i < 2) ? 0.25f : -0.25f;
                    var leg = Util.Pivot(root, new Vector3(sx, 0.32f, sz));
                    P(Cy, leg, sx * 0.25f, -0.14f, 0f, 0.1f, 0.15f, 0.1f, dark, 0f, 0f, sx > 0 ? 20f : -20f);
                    rig.legs.Add(leg);
                    rig.legPhase.Add(((i < 2) ? 0f : Mathf.PI) + ((i % 2 == 0) ? 0f : Mathf.PI));
                }
                break;
            }
        }
        return rig;
    }

    // 여성 테이머: 분홍 포니테일, 보라 원피스, 지팡이
    public static TamerRig BuildTamer(Transform parent)
    {
        var r = new TamerRig();
        var m = new GameObject("Model").transform;
        m.SetParent(parent, false);
        r.model = m;

        var entry = ModelLibrary.Find("player");
        if (entry != null)
        {
            var mdl = ModelLibrary.Spawn(entry.prefab, m, 1.75f * entry.heightMul, entry.yaw);
            r.anim = ModelAnimator.Setup(mdl, entry.clips);
            r.usesModel = true;
            AttachStaff(r, mdl, m);
            return r;
        }

        Color skin = new Color(1f, 0.86f, 0.76f);
        Color hair = new Color(1f, 0.56f, 0.72f);
        Color outfit = new Color(0.48f, 0.32f, 0.78f);
        Color white = new Color(0.97f, 0.97f, 1f);
        Color stocking = new Color(0.18f, 0.16f, 0.25f);
        Color boot = new Color(0.38f, 0.24f, 0.16f);
        Color gold = new Color(1f, 0.82f, 0.3f);
        Color eye = new Color(0.3f, 0.16f, 0.42f);

        // 다리
        r.legL = Util.Pivot(m, new Vector3(-0.11f, 0.86f, 0f));
        P(Cy, r.legL, 0f, -0.38f, 0f, 0.14f, 0.38f, 0.14f, stocking);
        P(Cu, r.legL, 0f, -0.8f, 0.05f, 0.17f, 0.12f, 0.26f, boot);
        r.legR = Util.Pivot(m, new Vector3(0.11f, 0.86f, 0f));
        P(Cy, r.legR, 0f, -0.38f, 0f, 0.14f, 0.38f, 0.14f, stocking);
        P(Cu, r.legR, 0f, -0.8f, 0.05f, 0.17f, 0.12f, 0.26f, boot);

        // 치마와 몸통
        P(Cy, m, 0f, 0.88f, 0f, 0.56f, 0.14f, 0.5f, outfit);
        P(Cy, m, 0f, 0.75f, 0f, 0.6f, 0.03f, 0.54f, white);
        P(Ca, m, 0f, 1.18f, 0f, 0.4f, 0.3f, 0.3f, outfit);
        P(Cu, m, 0f, 1.25f, 0.14f, 0.16f, 0.2f, 0.04f, white);
        P(S, m, 0f, 1.33f, 0.16f, 0.08f, 0.08f, 0.08f, gold);

        // 팔 + 지팡이
        r.armL = Util.Pivot(m, new Vector3(-0.27f, 1.4f, 0f));
        P(Ca, r.armL, 0f, -0.27f, 0f, 0.11f, 0.27f, 0.11f, outfit);
        P(S, r.armL, 0f, -0.56f, 0f, 0.1f, 0.1f, 0.1f, skin);
        r.armR = Util.Pivot(m, new Vector3(0.27f, 1.4f, 0f));
        P(Ca, r.armR, 0f, -0.27f, 0f, 0.11f, 0.27f, 0.11f, outfit);
        P(S, r.armR, 0f, -0.56f, 0f, 0.1f, 0.1f, 0.1f, skin);
        P(Cy, r.armR, 0f, -0.5f, 0.12f, 0.04f, 0.6f, 0.04f, boot);
        r.staffTip = P(S, r.armR, 0f, 0.12f, 0.12f, 0.15f, 0.15f, 0.15f, new Color(0.55f, 0.9f, 1f), 0f, 0f, 0f, true);

        // 머리
        P(S, m, 0f, 1.72f, 0f, 0.4f, 0.4f, 0.4f, skin);
        P(S, m, 0f, 1.78f, -0.06f, 0.45f, 0.43f, 0.43f, hair);
        P(Cu, m, 0f, 1.88f, 0.13f, 0.36f, 0.1f, 0.12f, hair, 12f);
        P(Cu, m, -0.19f, 1.62f, 0.02f, 0.07f, 0.3f, 0.16f, hair);
        P(Cu, m, 0.19f, 1.62f, 0.02f, 0.07f, 0.3f, 0.16f, hair);
        r.ponytail = Util.Pivot(m, new Vector3(0f, 1.84f, -0.2f));
        P(Ca, r.ponytail, 0f, -0.22f, -0.06f, 0.15f, 0.25f, 0.15f, hair, 15f);
        P(Cu, m, 0f, 1.88f, -0.22f, 0.22f, 0.08f, 0.06f, gold);
        P(S, m, -0.075f, 1.71f, 0.18f, 0.06f, 0.08f, 0.04f, eye);
        P(S, m, 0.075f, 1.71f, 0.18f, 0.06f, 0.08f, 0.04f, eye);
        P(S, m, -0.12f, 1.65f, 0.165f, 0.06f, 0.03f, 0.02f, new Color(1f, 0.62f, 0.66f));
        P(S, m, 0.12f, 1.65f, 0.165f, 0.06f, 0.03f, 0.02f, new Color(1f, 0.62f, 0.66f));
        return r;
    }

    // 실제 모델의 오른손에 지팡이를 쥐여 준다 (손을 못 찾으면 몸 옆에)
    static void AttachStaff(TamerRig r, GameObject mdl, Transform fallback)
    {
        Transform hand = null;
        var animator = mdl.GetComponentInChildren<Animator>();
        if (animator != null && animator.isHuman) hand = animator.GetBoneTransform(HumanBodyBones.RightHand);
        if (hand == null)
        {
            foreach (var t in mdl.GetComponentsInChildren<Transform>())
            {
                string n = t.name.ToLower();
                if (n.Contains("hand") && (n.Contains("right") || n.EndsWith(".r") || n.EndsWith("_r") || n.EndsWith("r")))
                {
                    hand = t;
                    break;
                }
            }
        }
        var staff = new GameObject("Staff").transform;
        staff.position = hand != null ? hand.position : fallback.position + fallback.right * 0.35f + Vector3.up * 0.9f;
        staff.rotation = fallback.rotation;
        staff.SetParent(hand != null ? hand : fallback, true);
        var stick = Util.Part(PrimitiveType.Cylinder, null, Vector3.zero, new Vector3(0.04f, 0.6f, 0.04f), new Color(0.38f, 0.24f, 0.16f));
        stick.position = staff.position;
        stick.rotation = staff.rotation;
        stick.SetParent(staff, true);
        r.staffTip = Util.Part(PrimitiveType.Sphere, null, Vector3.zero, Vector3.one * 0.15f, new Color(0.55f, 0.9f, 1f), default(Vector3), true);
        r.staffTip.position = staff.position + Vector3.up * 0.62f;
        r.staffTip.SetParent(staff, true);
    }
}
