using UnityEngine;

namespace Taming
{
    public enum Element { Fire, Water, Grass, Earth, Wind, Light, Dark }

    public static class ElementChart
    {
        // 불 > 풀 > 대지 > 바람 > 물 > 불 순환, 빛 ↔ 어둠 서로 약점
        static bool Beats(Element a, Element b)
        {
            switch (a)
            {
                case Element.Fire: return b == Element.Grass;
                case Element.Grass: return b == Element.Earth;
                case Element.Earth: return b == Element.Wind;
                case Element.Wind: return b == Element.Water;
                case Element.Water: return b == Element.Fire;
                case Element.Light: return b == Element.Dark;
                case Element.Dark: return b == Element.Light;
                default: return false;
            }
        }

        public static float Multiplier(Element attacker, Element defender)
        {
            if (Beats(attacker, defender)) return 1.5f;
            if (attacker != Element.Light && attacker != Element.Dark && Beats(defender, attacker)) return 0.7f;
            return 1f;
        }

        public static string KoreanName(Element e)
        {
            switch (e)
            {
                case Element.Fire: return "불";
                case Element.Water: return "물";
                case Element.Grass: return "풀";
                case Element.Earth: return "대지";
                case Element.Wind: return "바람";
                case Element.Light: return "빛";
                default: return "어둠";
            }
        }

        public static Color ColorOf(Element e)
        {
            switch (e)
            {
                case Element.Fire: return new Color(1f, 0.45f, 0.15f);
                case Element.Water: return new Color(0.3f, 0.6f, 1f);
                case Element.Grass: return new Color(0.4f, 0.9f, 0.35f);
                case Element.Earth: return new Color(0.75f, 0.55f, 0.3f);
                case Element.Wind: return new Color(0.5f, 0.95f, 0.85f);
                case Element.Light: return new Color(1f, 0.92f, 0.55f);
                default: return new Color(0.6f, 0.4f, 0.9f);
            }
        }
    }
}
