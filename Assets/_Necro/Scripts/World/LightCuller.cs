using System.Collections.Generic;
using UnityEngine;

namespace Necro
{
    // 점광원·스포트라이트가 많을 때 주인공에서 먼 것을 꺼서 Forward+ 의 광원 목록 비용을 줄인다.
    // 오픈월드에는 등불·제단·도깨비불 광원이 수백 개 있다. 1장 월드의 안개는 옅어서 (밀도 0.0048, 100 m 밖에서도 빛이 80% 남는다)
    // 멀리 있는 광원도 안개에 묻히지 않는다. 그냥 끄면 빛 웅덩이가 툭 사라지므로, 경계에서 세기를 서서히 줄여 끈다.
    //  - 광원마다 끄는 거리를 따로 둔다: 끄는 거리 = 빛 범위(range) × rangeFactor (minRadius ~ maxRadius).
    //    범위가 큰 제단·등불은 멀리까지 켜 두고, 범위가 작은 버섯·연꽃·초는 가까이에서만 켠다.
    //  - LightCullDistance 가 붙은 광원(장면·장소의 '등대 빛')은 그 far 거리에서 끈다 (range 는 그대로라 그리기 비용은 같다).
    //    멀리서 보이는 것이 목적이라 줄이는 구간은 farFadeFraction (기본 0.2: 140 m 면 112 m 부터 줄어 140 m 에서 0).
    //  - 끄는 거리 바깥쪽 구간(fadeFraction)에서 세기를 1 → 0 으로 줄인다. 켤 때도 0 에서 시작하므로 툭 나타나지 않는다.
    //    끄는 것은 끄는 거리 + hysteresis 를 벗어난 뒤 (이미 세기 0) 라서 보이지 않는다.
    //  - 동시에 켜 둘 개수(maxActive)를 넘으면 (거리 / 끄는 거리) 비율이 작은 순으로 남긴다.
    //    밀려난 광원은 fadeSeconds 에 걸쳐 줄인 뒤 끈다.
    // 켜고 끌 광원 고르기는 interval 마다 한 번, 세기 줄이기는 켜져 있는 광원(많아야 maxActive 남짓)만 매 프레임 한다.
    // 배열은 Refresh 에서 미리 만들어 두어 실행 중에는 할당하지 않는다.
    // ※ 처음 모을 때 꺼져 있던 광원(다른 연출이 일부러 끈 것)은 건드리지 않는다. 실행 중에 다른 코드가 끈 광원도 그때부터 손을 뗀다.
    // ※ SoulFlicker 가 붙은 광원은 SoulFlicker.fade 로 세기를 줄인다. 없는 광원은 컬러가 세기를 직접 쓴다
    //    (켜 둔 동안 다른 코드가 그 세기를 바꾸면 덮어쓴다. 세기를 바꾸는 연출이 필요한 광원에는 SoulFlicker 를 붙인다).
    public class LightCuller : MonoBehaviour
    {
        [Header("대상")]
        [Tooltip("주인공. 비워 두면 시작할 때 이름이 'Player' 인 오브젝트를 한 번 찾는다")]
        public Transform target;

        [Header("컬링")]
        [Tooltip("켜고 끌 광원을 고르는 간격 (초). 세기를 서서히 바꾸는 것은 매 프레임 한다")]
        [Range(0.1f, 3f)] public float interval = 0.5f;
        [Tooltip("동시에 켜 둘 최대 개수 ((거리 / 끄는 거리) 비율이 작은 순). 밀려난 광원이 줄어드는 동안은 잠깐 넘을 수 있다.\n" +
                 "1장 월드는 생성기(trim_lights)가 걸을 수 있는 땅 어디서도 켜 둘 후보(끄는 거리 + 여유 안의 광원)가 46 개를 넘지 않게 맞춘다 (등대 빛 포함)")]
        [Range(4, 256)] public int maxActive = 48;

        [Header("광원별 끄는 거리")]
        [Tooltip("끄는 거리 = 광원의 빛 범위(range) × 이 값. 12 이면 범위 9 m 등불은 108 m 밖에서 꺼진다")]
        [Range(1f, 40f)] public float rangeFactor = 12f;
        [Tooltip("끄는 거리의 최소 (m). 범위가 작은 광원(버섯·연꽃·초)은 이 거리 안에서만 켜진다")]
        [Range(5f, 200f)] public float minRadius = 30f;
        [Tooltip("끄는 거리의 최대 (m). 제단처럼 범위가 큰 광원도 이 거리 밖에서는 꺼진다")]
        [Range(20f, 600f)] public float maxRadius = 200f;
        [Tooltip("켜진 광원은 끄는 거리 + 이 거리(m)까지 켜 둔다 (경계에서 켜고 끄기를 되풀이하지 않게). 이 구간에서는 세기가 이미 0 이다")]
        [Range(0f, 40f)] public float hysteresis = 10f;

        [Header("서서히 줄이기")]
        [Tooltip("끄는 거리 안쪽의 이 비율 구간에서 세기를 1 → 0 으로 줄인다 (0.3 이면 끄는 거리의 70% 지점부터 줄기 시작한다)")]
        [Range(0.05f, 1f)] public float fadeFraction = 0.3f;
        [Tooltip("LightCullDistance 로 끄는 거리를 덮어쓴 등대 빛의 줄이는 구간 비율 (0.2 면 140 m 등대 빛은 112 m 부터 줄어든다)")]
        [Range(0.05f, 1f)] public float farFadeFraction = 0.2f;
        [Tooltip("개수 제한에 밀려 끄거나 새로 켤 때 세기를 바꾸는 데 걸리는 시간 (초). 0 이면 바로 바뀐다")]
        [Range(0f, 2f)] public float fadeSeconds = 0.4f;

        [Header("대상 광원")]
        [Tooltip("시작할 때 장면의 점광원·스포트라이트를 모두 모은다 (꺼 두면 아래 목록만)")]
        public bool collectOnStart = true;
        [Tooltip("직접 지정한 광원 (collectOnStart 와 함께 쓰면 합쳐진다)")]
        public List<Light> lights = new List<Light>();

        // 지금 켜져 있는 광원 수 (서서히 줄어드는 중인 것 포함)
        public int ActiveCount { get { return liveCount; } }
        public int TotalCount { get { return cached != null ? cached.Length : 0; } }

        Light[] cached;
        Transform[] xf;
        SoulFlicker[] flickers;
        float[] baseIntensity;  // SoulFlicker 가 없는 광원의 원래 세기
        float[] cullR;          // 끄는 거리 (m)
        float[] keepR2;         // 켜진 광원을 유지하는 거리의 제곱 ((끄는 거리 + hysteresis)²)
        float[] invBand;        // 1 / 줄이는 구간 길이 (m)
        float[] timeFade;       // 시간에 따른 세기 (0 → 1). 개수 제한에 밀려나거나 새로 켤 때 쓴다
        float[] applied;        // 마지막으로 쓴 세기 비율 (같으면 다시 쓰지 않는다)
        bool[] managed;         // 컬러가 켜고 끄는 광원인가 (처음부터 꺼져 있던 광원은 false)
        bool[] want;            // 이번 판단에서 켜 두기로 고른 광원
        bool[] lit;             // 컬러가 켜 둔 광원
        int[] live;             // 켜져 있는 광원 번호 (매 프레임 세기를 계산할 대상)
        int liveCount;
        int[] topIndex;
        float[] topKey;
        float timer;

        void Start()
        {
            if (target == null)
            {
                var p = GameObject.Find("Player");     // Start 에서 한 번만 찾는다
                if (p != null) target = p.transform;
            }
            Refresh();
        }

        // 광원 목록을 다시 모은다 (장면에 광원을 새로 만든 뒤 부른다. 할당이 있으므로 매 프레임 부르지 않는다)
        public void Refresh()
        {
            // 컬러가 끄거나 줄여 둔 광원을 먼저 원래대로 돌린다.
            // 그래야 다시 모을 때 '컬러가 끈 광원'과 '처음부터 꺼져 있던 광원'을 구분할 수 있다.
            Restore();

            var found = new List<Light>();
            var seen = new HashSet<Light>();
            foreach (var l in lights) if (l != null && seen.Add(l)) found.Add(l);
            if (collectOnStart)
            {
#if UNITY_2023_1_OR_NEWER
                var all = Object.FindObjectsByType<Light>(FindObjectsSortMode.None);
#else
                var all = Object.FindObjectsOfType<Light>();
#endif
                foreach (var l in all)
                    if (l != null && (l.type == LightType.Point || l.type == LightType.Spot) && seen.Add(l)) found.Add(l);
            }

            int n = found.Count;
            cached = found.ToArray();
            xf = new Transform[n];
            flickers = new SoulFlicker[n];
            baseIntensity = new float[n];
            cullR = new float[n];
            keepR2 = new float[n];
            invBand = new float[n];
            timeFade = new float[n];
            applied = new float[n];
            managed = new bool[n];
            want = new bool[n];
            lit = new bool[n];
            live = new int[n];
            liveCount = 0;
            topIndex = new int[Mathf.Max(1, maxActive)];
            topKey = new float[topIndex.Length];

            float lo = Mathf.Max(1f, minRadius);
            float hi = Mathf.Max(lo, maxRadius);
            for (int i = 0; i < n; i++)
            {
                var l = cached[i];
                xf[i] = l.transform;
                managed[i] = l.enabled;            // 처음부터 꺼져 있던 광원은 다른 연출이 끈 것으로 보고 건드리지 않는다
                lit[i] = managed[i];
                var f = l.GetComponent<SoulFlicker>();
                flickers[i] = (f != null && f.enabled) ? f : null;   // 일부러 꺼 둔 일렁임은 켜지 않는다 (세기는 컬러가 직접 쓴다)
                baseIntensity[i] = l.intensity;
                // 등대 빛: LightCullDistance 의 far 에서 끈다 (Refresh 에서 한 번만 읽는다)
                var o = l.GetComponent<LightCullDistance>();
                bool far = o != null && o.enabled && o.far > 0f;
                float r = Mathf.Clamp(far ? o.far : l.range * rangeFactor, lo, hi);
                cullR[i] = r;
                keepR2[i] = (r + hysteresis) * (r + hysteresis);
                invBand[i] = 1f / Mathf.Max(0.5f, r * (far ? farFadeFraction : fadeFraction));
                timeFade[i] = 1f;
                applied[i] = 1f;
            }

            timer = interval;
            if (isActiveAndEnabled) Snap();
        }

        void OnEnable()
        {
            // 껐다 다시 켠 경우 (OnDisable 에서 모두 켜 두었다) 바로 다시 고른다. 처음 켜질 때는 Start 의 Refresh 가 한다
            if (cached != null) Snap();
        }

        void OnDisable()
        {
            // 컬러를 끄면 컬러가 맡은 광원을 모두 원래대로 켠다 (처음부터 꺼져 있던 광원은 그대로)
            Restore();
        }

        void Update()
        {
            if (cached == null || target == null) return;
            timer -= Time.deltaTime;
            if (timer <= 0f)
            {
                timer = interval;
                Cull(false);
            }
            UpdateFades(Time.deltaTime);
        }

        // 기다리지 않고 바로 고르고 세기를 맞춘다 (시작할 때, 다시 켤 때)
        void Snap()
        {
            if (cached == null || target == null) return;
            Cull(true);
            UpdateFades(0f);
        }

        // 켜 둘 광원을 고른다. snap 이면 고르지 않은 광원은 바로 끄고, 고른 광원은 시간 페이드 없이 켠다.
        void Cull(bool snap)
        {
            int cap = Mathf.Min(maxActive, topIndex.Length);
            int count = 0;
            Vector3 c = target.position;

            // 끄는 거리 안의 광원 중 (거리 / 끄는 거리)² 가 작은 cap 개를 고른다 (정렬된 고정 배열에 끼워 넣기)
            for (int i = 0; i < cached.Length; i++)
            {
                want[i] = false;
                if (!managed[i] || cached[i] == null) continue;
                float d = (xf[i].position - c).sqrMagnitude;
                float r2 = cullR[i] * cullR[i];
                if (d > (lit[i] ? keepR2[i] : r2)) continue;
                float key = d / r2;
                int j;
                if (count < cap) j = count++;
                else if (cap > 0 && key < topKey[cap - 1]) j = cap - 1;
                else continue;
                while (j > 0 && topKey[j - 1] > key) { topKey[j] = topKey[j - 1]; topIndex[j] = topIndex[j - 1]; j--; }
                topKey[j] = key; topIndex[j] = i;
            }
            for (int k = 0; k < count; k++) want[topIndex[k]] = true;

            liveCount = 0;
            for (int i = 0; i < cached.Length; i++)
            {
                if (!managed[i]) continue;
                var l = cached[i];
                if (l == null || (lit[i] && !l.enabled)) { Release(i); continue; }   // 지워졌거나 다른 코드가 끈 광원
                if (want[i])
                {
                    if (!lit[i]) TurnOn(i, snap ? 1f : 0f);
                    else if (snap) timeFade[i] = 1f;
                }
                else if (lit[i] && snap) TurnOff(i);
                // 고르지 않았지만 켜져 있는 광원은 UpdateFades 에서 서서히 줄인 뒤 끈다
                if (lit[i]) live[liveCount++] = i;
            }
        }

        // 켜져 있는 광원만 돌며 세기 = 거리 페이드 × 시간 페이드 를 쓴다 (할당 없음)
        void UpdateFades(float dt)
        {
            Vector3 c = target.position;
            float step = fadeSeconds > 0.001f ? dt / fadeSeconds : 1f;
            for (int k = liveCount - 1; k >= 0; k--)
            {
                int i = live[k];
                var l = cached[i];
                if (l == null || !l.enabled) { Release(i); live[k] = live[--liveCount]; continue; }

                float dist = (xf[i].position - c).magnitude;
                float df = Mathf.Clamp01((cullR[i] - dist) * invBand[i]);
                float tf = timeFade[i];
                if (want[i]) tf = Mathf.Min(1f, tf + step);
                else
                {
                    tf -= step;
                    // 다 줄었거나 이미 거리 페이드로 보이지 않으면 끈다
                    if (tf <= 0f || df <= 0f) { TurnOff(i); live[k] = live[--liveCount]; continue; }
                }
                timeFade[i] = tf;
                SetFade(i, df * tf);
            }
        }

        void SetFade(int i, float f)
        {
            if (applied[i] == f) return;
            applied[i] = f;
            var fl = flickers[i];
            if (fl != null) fl.fade = f;
            else cached[i].intensity = baseIntensity[i] * f;
        }

        void TurnOn(int i, float startFade)
        {
            var l = cached[i];
            var fl = flickers[i];
            timeFade[i] = startFade;
            applied[i] = -1f;               // 이번 프레임 UpdateFades 에서 반드시 세기를 쓴다
            if (fl != null) fl.fade = 0f;
            // 켜지는 순간 이전 세기가 한 프레임 보이지 않게 0 으로 둔다.
            // 단 SoulFlicker 는 Awake 에서 원래 세기를 읽으므로, 오브젝트가 아직 켜진 적 없으면 건드리지 않는다
            if (fl == null || l.gameObject.activeInHierarchy) l.intensity = 0f;
            l.enabled = true;
            if (fl != null) fl.enabled = true;
            lit[i] = true;
        }

        void TurnOff(int i)
        {
            var l = cached[i];
            var fl = flickers[i];
            if (fl != null) { fl.fade = 1f; fl.enabled = false; }
            else if (l != null) l.intensity = baseIntensity[i];   // 꺼져 있는 동안은 원래 세기로 둔다
            if (l != null) l.enabled = false;
            lit[i] = false;
            want[i] = false;
            timeFade[i] = 0f;
            applied[i] = 1f;
        }

        // 지워졌거나 다른 코드가 끈 광원: 세기만 원래대로 돌리고 더는 관리하지 않는다
        void Release(int i)
        {
            var l = cached[i];
            var fl = flickers[i];
            if (fl != null) fl.fade = 1f;
            else if (l != null) l.intensity = baseIntensity[i];
            managed[i] = false;
            lit[i] = false;
            want[i] = false;
        }

        // 컬러가 맡은 광원을 모두 원래 상태(켜짐, 원래 세기)로 돌린다
        void Restore()
        {
            if (cached == null) return;
            for (int i = 0; i < cached.Length; i++)
            {
                if (!managed[i]) continue;
                var l = cached[i];
                var fl = flickers[i];
                if (fl != null) { fl.fade = 1f; fl.enabled = true; }
                if (l != null)
                {
                    if (fl == null) l.intensity = baseIntensity[i];
                    l.enabled = true;
                }
                lit[i] = true;
                want[i] = false;
                timeFade[i] = 1f;
                applied[i] = 1f;
            }
            liveCount = 0;
        }
    }
}
