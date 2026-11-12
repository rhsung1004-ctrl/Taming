using System.Collections.Generic;
using UnityEngine;

namespace Necro.Proto
{
    // 유닛 몸체 애니메이션 (다리·팔 흔들기, 날갯짓, 꼬리, 공격 동작)
    public class Rig
    {
        public Transform root;
        public readonly List<Transform> legs = new List<Transform>();
        public readonly List<float> legPhase = new List<float>();
        public Transform armL, armR, wingL, wingR, tail;
        public bool humanoid;
        public float lunge;         // 1 → 0 으로 줄어드는 공격 동작 타이머
        public float rise = 1f;     // 0 → 1 땅에서 솟아나는 연출
        float scale = 1f;
        float phase;

        public Rig(float scale) { this.scale = scale; phase = Random.value * 10f; }

        public void Attack() { lunge = 1f; }

        public void Animate(float move01, bool flying, float dt)
        {
            float t = Time.time + phase;
            for (int i = 0; i < legs.Count; i++)
            {
                float a = flying ? 30f : Mathf.Sin(t * 10f + legPhase[i]) * 34f * move01;
                legs[i].localRotation = Quaternion.Euler(a, 0f, 0f);
            }
            lunge = Mathf.MoveTowards(lunge, 0f, dt * 3.5f);
            float swing = Mathf.Sin(lunge * Mathf.PI);
            if (humanoid)
            {
                float a = Mathf.Sin(t * 10f) * 28f * move01;
                if (armL != null) armL.localRotation = Quaternion.Euler(a, 0f, -6f);
                if (armR != null) armR.localRotation = Quaternion.Euler(-a - swing * 120f, 0f, 6f);
            }
            if (wingL != null)
            {
                float flap = flying ? Mathf.Sin(t * 6f) * 38f : 14f + Mathf.Sin(t * 1.6f) * 4f;
                wingL.localRotation = Quaternion.Euler(0f, 0f, flap);
                wingR.localRotation = Quaternion.Euler(0f, 0f, -flap);
            }
            if (tail != null) tail.localRotation = Quaternion.Euler(0f, Mathf.Sin(t * 3f) * (12f + 14f * move01), 0f);

            if (rise < 1f) rise = Mathf.Min(1f, rise + dt * 1.8f);
            if (root != null)
            {
                float e = 1f - (1f - rise) * (1f - rise);
                root.localScale = Vector3.one * scale * Mathf.Lerp(0.2f, 1f, e);
                root.localPosition = new Vector3(0f, (flying ? Mathf.Sin(t * 3f) * 0.12f : 0f) - (1f - e) * 1.2f * scale,
                                                 humanoid ? 0f : swing * 0.4f * scale);
            }
        }

        // 시체: 옆으로 눕힌다
        public void LieDown()
        {
            root.localRotation = Quaternion.Euler(0f, 0f, 90f);
            root.localPosition = new Vector3(0f, 0.25f * scale, 0f);
        }
    }

    // 주인공(여성 사령술사) 애니메이션
    public class HeroRig
    {
        public Transform model, legL, legR, armL, armR, hair, staffTip;
        public float seat;      // 탈것에 탔을 때 모델을 올리는 높이
        public float cast;      // 1 → 0 시전 동작

        public void Animate(float move, bool riding, bool airborne, float dt)
        {
            float t = Time.time;
            cast = Mathf.MoveTowards(cast, 0f, dt * 4f);
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
            if (cast > 0f) armR.localRotation = Quaternion.Euler(-110f * cast, 0f, 8f);
            hair.localRotation = Quaternion.Euler(Mathf.Sin(t * 5f) * 5f + move * 16f, Mathf.Sin(t * 3f) * 5f, 0f);
            model.localPosition = new Vector3(0f, seat + bob, 0f);
        }
    }

    // 에셋 없이 기본 도형으로 캐릭터를 조립한다. 본편에서 실제 3D 모델로 교체할 자리.
    public static class Body
    {
        const PrimitiveType S = PrimitiveType.Sphere;
        const PrimitiveType Cu = PrimitiveType.Cube;
        const PrimitiveType Cy = PrimitiveType.Cylinder;
        const PrimitiveType Ca = PrimitiveType.Capsule;

        static Transform P(PrimitiveType t, Transform parent, float x, float y, float z, float sx, float sy, float sz, Color c,
                           float rx = 0f, float ry = 0f, float rz = 0f, bool glow = false)
        {
            return Util.Part(t, parent, new Vector3(x, y, z), new Vector3(sx, sy, sz), c, new Vector3(rx, ry, rz), glow);
        }

        // 색 묶음: 적은 바랜 뼈 + 붉은 눈, 지배한 소환수는 보랏빛 뼈 + 영혼 불꽃
        struct Pal { public Color bone, dark, cloth, metal, eye; }

        static Pal Palette(bool ally)
        {
            if (ally)
                return new Pal
                {
                    bone = new Color(0.66f, 0.6f, 0.86f), dark = new Color(0.27f, 0.22f, 0.42f),
                    cloth = new Color(0.2f, 0.14f, 0.32f), metal = new Color(0.36f, 0.32f, 0.52f),
                    eye = new Color(0.72f, 0.45f, 1f)
                };
            return new Pal
            {
                bone = new Color(0.86f, 0.83f, 0.74f), dark = new Color(0.4f, 0.37f, 0.33f),
                cloth = new Color(0.3f, 0.22f, 0.18f), metal = new Color(0.42f, 0.43f, 0.46f),
                eye = new Color(1f, 0.25f, 0.15f)
            };
        }

        public static float AimHeight(Shape s)
        {
            switch (s) { case Shape.Wolf: return 0.7f; case Shape.Dragon: return 1.3f; default: return 1.15f; }
        }

        public static float SeatHeight(Shape s) { return s == Shape.Dragon ? 1.5f : 0.9f; }

        public static Rig Build(UnitDef d, bool ally, Transform parent, float scaleMul = 1f)
        {
            float scale = d.size * scaleMul;
            var rig = new Rig(scale);
            var root = new GameObject("Body").transform;
            root.SetParent(parent, false);
            root.localScale = Vector3.one * scale;
            rig.root = root;
            Pal p = Palette(ally);
            switch (d.shape)
            {
                case Shape.Wolf: BuildWolf(rig, root, p, ally); break;
                case Shape.Dragon: BuildDragon(rig, root, p, ally); break;
                default: BuildHumanoid(rig, root, p, d.shape); break;
            }
            return rig;
        }

        static void BuildHumanoid(Rig rig, Transform root, Pal p, Shape shape)
        {
            rig.humanoid = true;
            for (int i = 0; i < 2; i++)
            {
                float sx = i == 0 ? -0.1f : 0.1f;
                var leg = Util.Pivot(root, new Vector3(sx, 0.85f, 0f));
                P(Cy, leg, 0f, -0.42f, 0f, 0.07f, 0.42f, 0.07f, p.bone);
                P(Cu, leg, 0f, -0.83f, 0.05f, 0.1f, 0.05f, 0.2f, p.dark);
                rig.legs.Add(leg);
                rig.legPhase.Add(i * Mathf.PI);
            }
            P(Cu, root, 0f, 0.88f, 0f, 0.3f, 0.1f, 0.16f, p.bone);
            P(Cy, root, 0f, 1.15f, 0f, 0.06f, 0.25f, 0.06f, p.bone);
            for (int i = 0; i < 3; i++) P(Cu, root, 0f, 1.06f + i * 0.12f, 0f, 0.28f + i * 0.04f, 0.05f, 0.2f, p.bone);
            P(Cu, root, 0f, 1.42f, 0f, 0.44f, 0.06f, 0.12f, p.bone);
            P(S, root, 0f, 1.62f, 0.02f, 0.3f, 0.32f, 0.3f, p.bone);
            P(Cu, root, 0f, 1.5f, 0.06f, 0.18f, 0.06f, 0.16f, p.bone);
            P(S, root, -0.07f, 1.64f, 0.14f, 0.07f, 0.07f, 0.05f, p.eye, 0f, 0f, 0f, true);
            P(S, root, 0.07f, 1.64f, 0.14f, 0.07f, 0.07f, 0.05f, p.eye, 0f, 0f, 0f, true);

            rig.armL = Util.Pivot(root, new Vector3(-0.24f, 1.42f, 0f));
            P(Cy, rig.armL, 0f, -0.3f, 0f, 0.055f, 0.3f, 0.055f, p.bone);
            rig.armR = Util.Pivot(root, new Vector3(0.24f, 1.42f, 0f));
            P(Cy, rig.armR, 0f, -0.3f, 0f, 0.055f, 0.3f, 0.055f, p.bone);

            switch (shape)
            {
                case Shape.Skeleton:
                    P(Cu, rig.armR, 0f, -0.6f, 0.32f, 0.05f, 0.04f, 0.7f, p.metal);
                    P(Cu, rig.armR, 0f, -0.6f, 0.02f, 0.2f, 0.04f, 0.05f, p.dark);
                    break;
                case Shape.Archer:
                    P(Cu, rig.armL, 0f, -0.58f, 0.12f, 0.04f, 0.95f, 0.04f, p.cloth, 10f);
                    P(S, root, 0f, 1.66f, -0.05f, 0.36f, 0.36f, 0.36f, p.cloth);
                    P(Cu, root, 0.12f, 1.2f, -0.16f, 0.12f, 0.4f, 0.08f, p.cloth, 0f, 0f, -15f);
                    break;
                case Shape.Knight:
                    P(Cu, root, 0f, 1.2f, 0f, 0.44f, 0.42f, 0.27f, p.metal);
                    P(S, root, -0.3f, 1.46f, 0f, 0.24f, 0.2f, 0.26f, p.metal);
                    P(S, root, 0.3f, 1.46f, 0f, 0.24f, 0.2f, 0.26f, p.metal);
                    P(Cu, root, 0f, 1.68f, -0.02f, 0.3f, 0.2f, 0.32f, p.metal);
                    P(Cu, root, 0f, 1.86f, -0.04f, 0.05f, 0.16f, 0.3f, p.eye, 0f, 0f, 0f, true);
                    P(Cu, rig.armR, 0f, -0.6f, 0.55f, 0.09f, 0.04f, 1.25f, p.metal);
                    P(Cu, rig.armR, 0f, -0.6f, -0.02f, 0.3f, 0.05f, 0.06f, p.dark);
                    P(Cu, rig.armL, -0.08f, -0.42f, 0.08f, 0.05f, 0.5f, 0.4f, p.metal);
                    break;
                case Shape.Keeper:
                    P(Cy, root, 0f, 0.72f, 0f, 0.62f, 0.7f, 0.5f, p.cloth);
                    P(S, root, 0f, 1.3f, -0.12f, 0.6f, 0.5f, 0.5f, p.cloth);
                    P(Cy, root, 0f, 1.78f, 0f, 0.62f, 0.02f, 0.62f, p.dark);
                    P(Cy, root, 0f, 1.87f, 0f, 0.32f, 0.09f, 0.32f, p.dark);
                    P(S, rig.armL, 0f, -0.66f, 0.1f, 0.22f, 0.26f, 0.22f, new Color(0.5f, 1f, 0.55f), 0f, 0f, 0f, true);
                    P(Cy, rig.armR, 0f, -0.45f, 0.25f, 0.04f, 0.75f, 0.04f, p.dark, 20f);
                    P(Cu, rig.armR, 0f, -1.12f, 0f, 0.26f, 0.3f, 0.04f, p.metal, 20f);
                    break;
            }
        }

        static void BuildWolf(Rig rig, Transform root, Pal p, bool ally)
        {
            Color fur = ally ? p.bone : new Color(0.3f, 0.3f, 0.34f);
            Color dark = ally ? p.dark : new Color(0.18f, 0.18f, 0.22f);
            P(Ca, root, 0f, 0.65f, 0f, 0.46f, 0.55f, 0.46f, fur, 90f);
            P(S, root, 0f, 0.95f, 0.55f, 0.42f, 0.42f, 0.44f, fur);
            P(Cu, root, 0f, 0.88f, 0.82f, 0.18f, 0.15f, 0.28f, dark);
            P(Cu, root, -0.13f, 1.19f, 0.5f, 0.09f, 0.2f, 0.07f, dark, 0f, 0f, 12f);
            P(Cu, root, 0.13f, 1.19f, 0.5f, 0.09f, 0.2f, 0.07f, dark, 0f, 0f, -12f);
            P(S, root, -0.11f, 1.0f, 0.74f, 0.07f, 0.07f, 0.05f, p.eye, 0f, 0f, 0f, true);
            P(S, root, 0.11f, 1.0f, 0.74f, 0.07f, 0.07f, 0.05f, p.eye, 0f, 0f, 0f, true);
            for (int i = 0; i < 4; i++)
            {
                float sx = (i % 2 == 0) ? -0.16f : 0.16f;
                float sz = (i < 2) ? 0.32f : -0.32f;
                var leg = Util.Pivot(root, new Vector3(sx, 0.5f, sz));
                P(Cy, leg, 0f, -0.25f, 0f, 0.11f, 0.25f, 0.11f, dark);
                rig.legs.Add(leg);
                rig.legPhase.Add(((i < 2) ? 0f : Mathf.PI) + ((i % 2 == 0) ? 0f : Mathf.PI));
            }
            rig.tail = Util.Pivot(root, new Vector3(0f, 0.75f, -0.5f));
            P(Ca, rig.tail, 0f, 0.1f, -0.25f, 0.14f, 0.28f, 0.14f, fur, -60f);
        }

        // 적일 때는 살이 붙은 고룡, 지배하면 뼈만 남은 본드래곤
        static void BuildDragon(Rig rig, Transform root, Pal p, bool bone)
        {
            Color scale = new Color(0.42f, 0.13f, 0.12f), belly = new Color(0.62f, 0.42f, 0.28f), horn = new Color(0.85f, 0.8f, 0.7f);
            Color main = bone ? p.bone : scale;
            Color sub = bone ? p.dark : belly;
            Color membrane = bone ? new Color(0.3f, 0.18f, 0.5f) : new Color(0.3f, 0.08f, 0.08f);

            if (bone)
            {
                P(Cy, root, 0f, 1.3f, 0f, 0.14f, 0.95f, 0.14f, main, 90f);
                for (int i = 0; i < 6; i++)
                {
                    float z = -0.65f + i * 0.26f;
                    float w = 0.62f + Mathf.Sin(i / 5f * Mathf.PI) * 0.26f;
                    P(Cu, root, 0f, 1.22f, z, w, 0.06f, 0.07f, main);
                    P(Cu, root, -w * 0.5f, 0.95f, z, 0.06f, 0.56f, 0.07f, main, 0f, 0f, -8f);
                    P(Cu, root, w * 0.5f, 0.95f, z, 0.06f, 0.56f, 0.07f, main, 0f, 0f, 8f);
                }
                P(S, root, 0f, 0.98f, 0.05f, 0.42f, 0.42f, 0.6f, p.eye, 0f, 0f, 0f, true);   // 가슴 속 영혼 불꽃
            }
            else
            {
                P(Ca, root, 0f, 1.1f, 0f, 0.95f, 0.95f, 0.95f, main, 90f);
                P(Ca, root, 0f, 0.95f, 0.05f, 0.75f, 0.8f, 0.75f, sub, 90f);
                for (int i = 0; i < 5; i++) P(Cu, root, 0f, 1.62f, 0.6f - i * 0.32f, 0.07f, 0.24f, 0.16f, horn, 35f);
            }

            // 목과 머리
            P(Ca, root, 0f, 1.62f, 1.05f, bone ? 0.2f : 0.38f, 0.58f, bone ? 0.2f : 0.38f, main, 48f);
            P(Cu, root, 0f, 2.08f, 1.62f, 0.42f, 0.34f, 0.72f, main);
            P(Cu, root, 0f, 1.9f, 1.7f, 0.34f, 0.1f, 0.58f, bone ? main : sub);
            P(Cu, root, -0.16f, 2.36f, 1.32f, 0.07f, 0.07f, 0.46f, horn, -32f);
            P(Cu, root, 0.16f, 2.36f, 1.32f, 0.07f, 0.07f, 0.46f, horn, -32f);
            P(S, root, -0.2f, 2.14f, 1.78f, 0.1f, 0.1f, 0.08f, p.eye, 0f, 0f, 0f, true);
            P(S, root, 0.2f, 2.14f, 1.78f, 0.1f, 0.1f, 0.08f, p.eye, 0f, 0f, 0f, true);

            for (int i = 0; i < 4; i++)
            {
                float sx = (i % 2 == 0) ? -0.42f : 0.42f;
                float sz = (i < 2) ? 0.55f : -0.55f;
                var leg = Util.Pivot(root, new Vector3(sx, 0.92f, sz));
                P(Cy, leg, 0f, -0.44f, 0f, bone ? 0.1f : 0.22f, 0.46f, bone ? 0.1f : 0.22f, main);
                P(Cu, leg, 0f, -0.88f, 0.1f, 0.26f, 0.08f, 0.36f, bone ? main : sub);
                rig.legs.Add(leg);
                rig.legPhase.Add(((i < 2) ? 0f : Mathf.PI) + ((i % 2 == 0) ? 0f : Mathf.PI));
            }

            for (int side = -1; side <= 1; side += 2)
            {
                var wing = Util.Pivot(root, new Vector3(0.4f * side, 1.55f, 0.15f));
                P(Cu, wing, 1.15f * side, 0f, 0.25f, 2.3f, 0.08f, 0.1f, main);            // 날개뼈
                P(Cu, wing, 2.7f * side, 0f, 0.05f, 1.3f, 0.07f, 0.09f, main, 0f, -18f * side);
                P(Cu, wing, 1.2f * side, -0.02f, -0.3f, 2.2f, 0.03f, 1.0f, membrane);       // 날개막
                P(Cu, wing, 2.6f * side, -0.02f, -0.45f, 1.2f, 0.03f, 0.75f, membrane, 0f, -18f * side);
                if (side < 0) rig.wingL = wing; else rig.wingR = wing;
            }

            rig.tail = Util.Pivot(root, new Vector3(0f, 1.1f, -0.9f));
            P(Ca, rig.tail, 0f, 0f, -0.6f, bone ? 0.16f : 0.34f, 0.7f, bone ? 0.16f : 0.34f, main, 90f);
            P(Ca, rig.tail, 0f, -0.05f, -1.6f, bone ? 0.1f : 0.18f, 0.5f, bone ? 0.1f : 0.18f, main, 90f);
            P(Cu, rig.tail, 0f, -0.05f, -2.15f, 0.3f, 0.06f, 0.3f, horn, 0f, 45f);
        }

        // 여성 사령술사: 은보라 긴 머리, 검보라 로브, 영혼석 지팡이
        public static HeroRig BuildHero(Transform parent)
        {
            var r = new HeroRig();
            var m = new GameObject("Model").transform;
            m.SetParent(parent, false);
            r.model = m;

            Color skin = new Color(0.98f, 0.88f, 0.84f);
            Color hair = new Color(0.8f, 0.74f, 0.95f);
            Color robe = new Color(0.2f, 0.13f, 0.32f);
            Color trim = new Color(0.58f, 0.36f, 0.86f);
            Color stocking = new Color(0.1f, 0.09f, 0.15f);
            Color boot = new Color(0.16f, 0.12f, 0.2f);
            Color gold = new Color(0.95f, 0.8f, 0.4f);
            Color eye = new Color(0.62f, 0.3f, 0.95f);
            Color soul = new Color(0.72f, 0.45f, 1f);

            r.legL = Util.Pivot(m, new Vector3(-0.11f, 0.86f, 0f));
            P(Cy, r.legL, 0f, -0.38f, 0f, 0.14f, 0.38f, 0.14f, stocking);
            P(Cu, r.legL, 0f, -0.8f, 0.05f, 0.17f, 0.12f, 0.26f, boot);
            r.legR = Util.Pivot(m, new Vector3(0.11f, 0.86f, 0f));
            P(Cy, r.legR, 0f, -0.38f, 0f, 0.14f, 0.38f, 0.14f, stocking);
            P(Cu, r.legR, 0f, -0.8f, 0.05f, 0.17f, 0.12f, 0.26f, boot);

            P(Cy, m, 0f, 0.84f, 0f, 0.6f, 0.2f, 0.52f, robe);
            P(Cy, m, 0f, 0.65f, 0f, 0.66f, 0.02f, 0.58f, trim);
            P(Ca, m, 0f, 1.18f, 0f, 0.4f, 0.3f, 0.3f, robe);
            P(Cu, m, 0f, 1.25f, 0.14f, 0.1f, 0.24f, 0.04f, trim);
            P(S, m, 0f, 1.36f, 0.16f, 0.09f, 0.09f, 0.06f, soul, 0f, 0f, 0f, true);
            P(Cu, m, 0f, 1.05f, -0.2f, 0.5f, 0.75f, 0.05f, robe, 8f);        // 망토

            r.armL = Util.Pivot(m, new Vector3(-0.27f, 1.4f, 0f));
            P(Ca, r.armL, 0f, -0.27f, 0f, 0.11f, 0.27f, 0.11f, robe);
            P(S, r.armL, 0f, -0.56f, 0f, 0.1f, 0.1f, 0.1f, skin);
            r.armR = Util.Pivot(m, new Vector3(0.27f, 1.4f, 0f));
            P(Ca, r.armR, 0f, -0.27f, 0f, 0.11f, 0.27f, 0.11f, robe);
            P(S, r.armR, 0f, -0.56f, 0f, 0.1f, 0.1f, 0.1f, skin);
            P(Cy, r.armR, 0f, -0.45f, 0.12f, 0.04f, 0.72f, 0.04f, boot);
            P(Cu, r.armR, 0f, 0.24f, 0.12f, 0.2f, 0.05f, 0.05f, gold);
            r.staffTip = P(S, r.armR, 0f, 0.36f, 0.12f, 0.17f, 0.2f, 0.17f, soul, 0f, 0f, 0f, true);

            P(S, m, 0f, 1.72f, 0f, 0.4f, 0.4f, 0.4f, skin);
            P(S, m, 0f, 1.78f, -0.06f, 0.45f, 0.43f, 0.43f, hair);
            P(Cu, m, 0f, 1.88f, 0.13f, 0.36f, 0.1f, 0.12f, hair, 12f);
            P(Cu, m, -0.19f, 1.6f, 0.02f, 0.07f, 0.36f, 0.16f, hair);
            P(Cu, m, 0.19f, 1.6f, 0.02f, 0.07f, 0.36f, 0.16f, hair);
            r.hair = Util.Pivot(m, new Vector3(0f, 1.8f, -0.18f));
            P(Cu, r.hair, 0f, -0.42f, -0.05f, 0.36f, 0.8f, 0.1f, hair, 6f);
            // 부서진 왕관 조각
            P(Cu, m, 0f, 1.99f, 0.04f, 0.3f, 0.04f, 0.3f, gold);
            P(Cu, m, -0.1f, 2.05f, 0.14f, 0.05f, 0.1f, 0.05f, gold);
            P(Cu, m, 0.1f, 2.07f, 0.14f, 0.05f, 0.14f, 0.05f, gold);
            P(S, m, -0.075f, 1.71f, 0.18f, 0.06f, 0.08f, 0.04f, eye);
            P(S, m, 0.075f, 1.71f, 0.18f, 0.06f, 0.08f, 0.04f, eye);
            return r;
        }
    }
}
