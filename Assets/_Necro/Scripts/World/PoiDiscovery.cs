using UnityEngine;
using UnityEngine.InputSystem;

namespace Necro
{
    // 이름 있는 장소 하나 (월드 도구가 world.json 의 pois 로 채운다)
    [System.Serializable]
    public class NecroPoi
    {
        [Tooltip("장소 id (world.json 의 id)")] public string id;
        [Tooltip("화면에 보이는 이름")] public string name;
        [Tooltip("장소 중심 (월드 좌표)")] public Vector3 position;
        [Tooltip("이 반지름(m) 안에 들어오면 발견")] public float radius = 30f;
        [Tooltip("발견하면 지도에 표시")] public bool showOnMap = true;
        [System.NonSerialized] public bool discovered;
    }

    // 장소 발견 알림과 지도.
    //  - 이름 있는 장소에 처음 가까이 가면 화면 위에 "장소 발견" 띠가 뜬다
    //  - M (게임패드 Select) 로 지도를 켜고 끈다. 지도에 주인공 위치·방향과 발견한 장소가 보인다
    // ※ 임시 UI: 화면 표시는 IMGUI 로 그린 임시 구현이다. 본편 UI(UI Toolkit)가 생기면 표시 부분만 바꾼다.
    // ※ 발견 기록은 아직 저장하지 않는다 (저장 시스템이 생기면 연결).
    public class PoiDiscovery : MonoBehaviour
    {
        [Header("대상")]
        [Tooltip("주인공. 비워 두면 시작할 때 이름이 'Player' 인 오브젝트를 한 번 찾는다")]
        public Transform hero;

        [Header("장소 (월드 도구가 채운다)")]
        [Tooltip("이름 있는 장소 목록. 1장 오픈월드 만들기 도구가 world.json 의 pois 로 채운다")]
        public NecroPoi[] places = new NecroPoi[0];

        [Header("지도")]
        [Tooltip("지도 그림 (위 = 북쪽)")] public Texture2D mapTexture;
        [Tooltip("지도 그림 왼쪽 아래 모서리의 월드 좌표 (x, z)")] public Vector2 worldMin = Vector2.zero;
        [Tooltip("지도 그림이 덮는 월드 크기 (m)")] public Vector2 worldSize = new Vector2(2048f, 2048f);
        [Tooltip("지도가 화면 높이에서 차지하는 비율")] [Range(0.3f, 1f)] public float mapScreenHeight = 0.86f;
        [Tooltip("주인공 표시 색")] public Color heroColor = new Color(1f, 0.92f, 0.7f);
        [Tooltip("장소 표시 색")] public Color placeColor = new Color(0.78f, 0.5f, 1f);

        [Header("발견 알림")]
        [Tooltip("알림 띠가 떠 있는 시간 (초)")] [Range(1f, 10f)] public float bannerSeconds = 4.5f;
        [Tooltip("장소까지 거리를 재는 간격 (초)")] [Range(0.05f, 2f)] public float checkInterval = 0.25f;

        public bool MapOpen { get; private set; }
        public int DiscoveredCount { get; private set; }

        float checkTimer;
        int bannerIndex = -1;
        float bannerStart = -100f;
        string countText = "";
        Texture2D arrowTex, diamondTex, pixelTex;
        GUIStyle bannerTitle, bannerName, labelStyle, hintStyle;

        void Start()
        {
            if (hero == null)
            {
                var p = GameObject.Find("Player");     // Start 에서 한 번만 찾는다
                if (p != null) hero = p.transform;
            }
            if (places == null) places = new NecroPoi[0];
            arrowTex = MakeArrow(32);
            diamondTex = MakeDiamond(16);
            pixelTex = new Texture2D(1, 1, TextureFormat.RGBA32, false);
            pixelTex.SetPixel(0, 0, Color.white);
            pixelTex.Apply();
            RebuildCountText();
        }

        void OnDestroy()
        {
            if (arrowTex != null) Destroy(arrowTex);
            if (diamondTex != null) Destroy(diamondTex);
            if (pixelTex != null) Destroy(pixelTex);
        }

        void Update()
        {
            var k = Keyboard.current;
            var g = Gamepad.current;
            if ((k != null && k.mKey.wasPressedThisFrame) || (g != null && g.selectButton.wasPressedThisFrame))
                MapOpen = !MapOpen;

            checkTimer -= Time.deltaTime;
            if (checkTimer > 0f || hero == null) return;
            checkTimer = checkInterval;
            Vector3 hp = hero.position;
            for (int i = 0; i < places.Length; i++)
            {
                var poi = places[i];
                if (poi == null || poi.discovered) continue;
                float dx = hp.x - poi.position.x, dz = hp.z - poi.position.z;
                if (dx * dx + dz * dz <= poi.radius * poi.radius) Discover(i);
            }
        }

        public void Discover(int index)
        {
            if (index < 0 || index >= places.Length || places[index].discovered) return;
            places[index].discovered = true;
            DiscoveredCount++;
            bannerIndex = index;
            bannerStart = Time.unscaledTime;
            RebuildCountText();
        }

        void RebuildCountText()
        {
            countText = "발견한 장소 " + DiscoveredCount + " / " + places.Length + "      [M] 지도 닫기";
        }

        // ───────────── 임시 화면 표시 (IMGUI) ─────────────
        void OnGUI()
        {
            EnsureStyles();
            DrawBanner();
            if (MapOpen) DrawMap();
            else GUI.Label(new Rect(16f, Screen.height - 34f, 240f, 24f), "[M] 지도", hintStyle);
        }

        void EnsureStyles()
        {
            if (bannerTitle != null) return;
            bannerTitle = new GUIStyle(GUI.skin.label) { alignment = TextAnchor.MiddleCenter, fontSize = 18 };
            bannerTitle.normal.textColor = new Color(0.82f, 0.72f, 1f);
            bannerName = new GUIStyle(GUI.skin.label) { alignment = TextAnchor.MiddleCenter, fontSize = 34, fontStyle = FontStyle.Bold };
            bannerName.normal.textColor = Color.white;
            labelStyle = new GUIStyle(GUI.skin.label) { alignment = TextAnchor.MiddleLeft, fontSize = 15, fontStyle = FontStyle.Bold };
            labelStyle.normal.textColor = new Color(0.95f, 0.9f, 1f);
            hintStyle = new GUIStyle(GUI.skin.label) { alignment = TextAnchor.MiddleLeft, fontSize = 15 };
            hintStyle.normal.textColor = new Color(1f, 1f, 1f, 0.55f);
        }

        void DrawBanner()
        {
            if (bannerIndex < 0) return;
            float age = Time.unscaledTime - bannerStart;
            if (age > bannerSeconds) return;
            // 0.5초 동안 나타나고 마지막 0.8초 동안 사라진다
            float a = Mathf.Clamp01(age / 0.5f) * Mathf.Clamp01((bannerSeconds - age) / 0.8f);
            float w = Screen.width, y = Screen.height * 0.14f;
            Color old = GUI.color;
            GUI.color = new Color(0.03f, 0.01f, 0.07f, 0.62f * a);
            GUI.DrawTexture(new Rect(0f, y, w, 92f), pixelTex);
            GUI.color = new Color(0.7f, 0.45f, 1f, 0.8f * a);
            GUI.DrawTexture(new Rect(w * 0.3f, y + 4f, w * 0.4f, 1f), pixelTex);
            GUI.DrawTexture(new Rect(w * 0.3f, y + 87f, w * 0.4f, 1f), pixelTex);
            GUI.color = new Color(1f, 1f, 1f, a);
            GUI.Label(new Rect(0f, y + 8f, w, 24f), "장소 발견", bannerTitle);
            GUI.Label(new Rect(0f, y + 32f, w, 50f), places[bannerIndex].name, bannerName);
            GUI.color = old;
        }

        void DrawMap()
        {
            float size = Screen.height * mapScreenHeight;
            var rect = new Rect((Screen.width - size) * 0.5f, (Screen.height - size) * 0.5f, size, size);
            Color old = GUI.color;
            GUI.color = new Color(0f, 0f, 0f, 0.55f);
            GUI.DrawTexture(new Rect(0f, 0f, Screen.width, Screen.height), pixelTex);
            GUI.color = Color.white;
            if (mapTexture != null) GUI.DrawTexture(rect, mapTexture, ScaleMode.StretchToFill);
            else
            {
                GUI.color = new Color(0.08f, 0.06f, 0.12f, 0.95f);
                GUI.DrawTexture(rect, pixelTex);
                GUI.color = Color.white;
                GUI.Label(new Rect(rect.x + 16f, rect.y + 12f, size, 24f), "지도 그림(map.png)이 없습니다", labelStyle);
            }

            // 발견한 장소
            for (int i = 0; i < places.Length; i++)
            {
                var poi = places[i];
                if (poi == null || !poi.discovered || !poi.showOnMap) continue;
                Vector2 m = ToMap(rect, poi.position);
                GUI.color = placeColor;
                GUI.DrawTexture(new Rect(m.x - 7f, m.y - 7f, 14f, 14f), diamondTex);
                GUI.color = Color.black;
                GUI.Label(new Rect(m.x + 11f, m.y - 11f, 260f, 24f), poi.name, labelStyle);
                GUI.color = Color.white;
                GUI.Label(new Rect(m.x + 10f, m.y - 12f, 260f, 24f), poi.name, labelStyle);
            }

            // 주인공 위치와 방향 (위 = 북쪽, 시계 방향으로 돈다)
            if (hero != null)
            {
                Vector2 h = ToMap(rect, hero.position);
                Matrix4x4 saved = GUI.matrix;
                GUIUtility.RotateAroundPivot(hero.eulerAngles.y, h);
                GUI.color = heroColor;
                GUI.DrawTexture(new Rect(h.x - 12f, h.y - 12f, 24f, 24f), arrowTex);
                GUI.matrix = saved;
            }
            GUI.color = Color.white;
            GUI.Label(new Rect(rect.x, rect.yMax + 4f, size, 24f), countText, hintStyle);
            GUI.color = old;
        }

        Vector2 ToMap(Rect r, Vector3 world)
        {
            float u = (world.x - worldMin.x) / Mathf.Max(worldSize.x, 1f);
            float v = (world.z - worldMin.y) / Mathf.Max(worldSize.y, 1f);
            return new Vector2(r.x + Mathf.Clamp01(u) * r.width, r.y + (1f - Mathf.Clamp01(v)) * r.height);
        }

        // 위를 가리키는 화살촉
        static Texture2D MakeArrow(int n)
        {
            var t = new Texture2D(n, n, TextureFormat.RGBA32, false) { filterMode = FilterMode.Bilinear, wrapMode = TextureWrapMode.Clamp };
            for (int y = 0; y < n; y++)
                for (int x = 0; x < n; x++)
                {
                    // 텍스처 y 는 아래에서 위로. 꼭짓점이 위(y = n-1)
                    float fy = (y + 0.5f) / n, fx = Mathf.Abs((x + 0.5f) / n - 0.5f) * 2f;
                    bool inside = fx < (1f - fy) * 0.95f && fy > 0.08f && !(fy < 0.38f && fx < (0.38f - fy) * 1.8f);
                    t.SetPixel(x, y, inside ? Color.white : Color.clear);
                }
            t.Apply();
            return t;
        }

        static Texture2D MakeDiamond(int n)
        {
            var t = new Texture2D(n, n, TextureFormat.RGBA32, false) { filterMode = FilterMode.Bilinear, wrapMode = TextureWrapMode.Clamp };
            for (int y = 0; y < n; y++)
                for (int x = 0; x < n; x++)
                {
                    float d = Mathf.Abs((x + 0.5f) / n - 0.5f) + Mathf.Abs((y + 0.5f) / n - 0.5f);
                    t.SetPixel(x, y, d < 0.48f ? Color.white : Color.clear);
                }
            t.Apply();
            return t;
        }
    }
}
