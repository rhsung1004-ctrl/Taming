using System.Collections.Generic;
using UnityEngine;

namespace Necro
{
    // 점광원·스포트라이트가 많을 때 주인공에서 먼 것을 주기적으로 끈다.
    // 오픈월드에는 등불·제단·도깨비불 광원이 수백 개 있다. 멀리 있는 광원은 안개에 묻혀 보이지 않으므로
    // 가까운 것만 켜 두어 Forward+ 의 광원 목록과 그림자 비용을 줄인다.
    // 판단은 interval 마다 한 번, 배열을 미리 만들어 두어 실행 중에는 할당하지 않는다.
    public class LightCuller : MonoBehaviour
    {
        [Header("대상")]
        [Tooltip("주인공. 비워 두면 시작할 때 이름이 'Player' 인 오브젝트를 한 번 찾는다")]
        public Transform target;

        [Header("컬링")]
        [Tooltip("판단 간격 (초)")]
        [Range(0.1f, 3f)] public float interval = 0.5f;
        [Tooltip("이 거리(m) 안의 광원만 켠다")]
        [Range(10f, 400f)] public float radius = 80f;
        [Tooltip("켜진 광원은 반지름 + 이 거리(m)까지 유지한다 (경계에서 깜박이지 않게)")]
        [Range(0f, 40f)] public float hysteresis = 10f;
        [Tooltip("동시에 켜 둘 최대 개수 (가까운 순)")]
        [Range(4, 256)] public int maxActive = 48;

        [Header("대상 광원")]
        [Tooltip("시작할 때 장면의 점광원·스포트라이트를 모두 모은다 (꺼 두면 아래 목록만)")]
        public bool collectOnStart = true;
        [Tooltip("직접 지정한 광원 (collectOnStart 와 함께 쓰면 합쳐진다)")]
        public List<Light> lights = new List<Light>();

        public int ActiveCount { get; private set; }
        public int TotalCount { get { return cached != null ? cached.Length : 0; } }

        Light[] cached;
        Behaviour[] flickers;
        bool[] isOn;
        int[] topIndex;
        float[] topDist;
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
            var found = new List<Light>();
            foreach (var l in lights) if (l != null && !found.Contains(l)) found.Add(l);
            if (collectOnStart)
            {
#if UNITY_2023_1_OR_NEWER
                var all = Object.FindObjectsByType<Light>(FindObjectsSortMode.None);
#else
                var all = Object.FindObjectsOfType<Light>();
#endif
                foreach (var l in all)
                    if (l != null && (l.type == LightType.Point || l.type == LightType.Spot) && !found.Contains(l)) found.Add(l);
            }
            cached = found.ToArray();
            flickers = new Behaviour[cached.Length];
            isOn = new bool[cached.Length];
            for (int i = 0; i < cached.Length; i++)
            {
                flickers[i] = cached[i].GetComponent<SoulFlicker>();
                isOn[i] = cached[i].enabled;
            }
            topIndex = new int[Mathf.Max(1, maxActive)];
            topDist = new float[topIndex.Length];
            timer = 0f;
            Cull();
        }

        void Update()
        {
            timer -= Time.deltaTime;
            if (timer > 0f) return;
            timer = interval;
            Cull();
        }

        void Cull()
        {
            if (cached == null || target == null) return;
            int cap = Mathf.Min(maxActive, topIndex.Length);
            int count = 0;
            Vector3 c = target.position;
            float r0 = radius * radius;
            float r1 = (radius + hysteresis) * (radius + hysteresis);

            // 반지름 안의 광원 중 가까운 cap 개를 고른다 (정렬된 고정 배열에 끼워 넣기)
            for (int i = 0; i < cached.Length; i++)
            {
                var l = cached[i];
                if (l == null) continue;
                float d = (l.transform.position - c).sqrMagnitude;
                if (d > (isOn[i] ? r1 : r0)) continue;
                if (count < cap)
                {
                    int j = count++;
                    while (j > 0 && topDist[j - 1] > d) { topDist[j] = topDist[j - 1]; topIndex[j] = topIndex[j - 1]; j--; }
                    topDist[j] = d; topIndex[j] = i;
                }
                else if (cap > 0 && d < topDist[cap - 1])
                {
                    int j = cap - 1;
                    while (j > 0 && topDist[j - 1] > d) { topDist[j] = topDist[j - 1]; topIndex[j] = topIndex[j - 1]; j--; }
                    topDist[j] = d; topIndex[j] = i;
                }
            }

            for (int i = 0; i < isOn.Length; i++) isOn[i] = false;
            for (int k = 0; k < count; k++) isOn[topIndex[k]] = true;
            for (int i = 0; i < cached.Length; i++)
            {
                var l = cached[i];
                if (l == null) continue;
                if (l.enabled != isOn[i]) l.enabled = isOn[i];
                var f = flickers[i];
                if (f != null && f.enabled != isOn[i]) f.enabled = isOn[i];
            }
            ActiveCount = count;
        }

        void OnDisable()
        {
            // 컬러를 끄면 모든 광원을 다시 켠다
            if (cached == null) return;
            for (int i = 0; i < cached.Length; i++)
            {
                if (cached[i] != null) cached[i].enabled = true;
                if (flickers[i] != null) flickers[i].enabled = true;
                isOn[i] = true;
            }
        }
    }
}
