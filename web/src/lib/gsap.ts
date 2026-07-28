import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

let registered = false;
if (typeof window !== "undefined" && !registered) {
  gsap.registerPlugin(ScrollTrigger);
  gsap.defaults({ ease: "power2.out", duration: 0.5 });
  ScrollTrigger.config({ ignoreMobileResize: true });
  registered = true;
}

export const EASE = {
  out: "power2.out",
  inOut: "power3.inOut",
  bar: "power2.inOut",
} as const;

export const DUR = {
  fast: 0.3,
  base: 0.5,
  slow: 0.8,
  bar: 0.9,
} as const;

const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Fade + rise, fired when the element scrolls into view. */
export function revealOnScroll(
  targets: gsap.TweenTarget,
  opts: { y?: number; stagger?: number; delay?: number; start?: string } = {}
) {
  const { y = 16, stagger = 0.06, delay = 0, start = "top 88%" } = opts;
  if (prefersReducedMotion()) {
    gsap.set(targets, { opacity: 1, y: 0 });
    return;
  }
  return gsap.fromTo(
    targets,
    { opacity: 0, y },
    {
      opacity: 1,
      y: 0,
      duration: DUR.base,
      ease: EASE.out,
      stagger,
      delay,
      scrollTrigger: { trigger: targets as gsap.DOMTarget, start, once: true },
    }
  );
}

/** Grow a bar from zero to its data width, on scroll-in. */
export function growBars(selector: string, scope: HTMLElement) {
  const bars = scope.querySelectorAll<HTMLElement>(selector);
  bars.forEach((bar) => {
    const target = bar.dataset.width ?? "0%";
    if (prefersReducedMotion()) {
      bar.style.width = target;
      return;
    }
    gsap.fromTo(
      bar,
      { width: "0%" },
      {
        width: target,
        duration: DUR.bar,
        ease: EASE.bar,
        scrollTrigger: { trigger: bar, start: "top 95%", once: true },
      }
    );
  });
}

/** Count a number up to its final value. `format` renders each frame. */
export function countUp(
  el: HTMLElement,
  to: number,
  format: (n: number) => string,
  duration = DUR.slow
) {
  if (prefersReducedMotion()) {
    el.textContent = format(to);
    return;
  }
  const obj = { v: 0 };
  return gsap.to(obj, {
    v: to,
    duration,
    ease: EASE.out,
    onUpdate: () => {
      el.textContent = format(obj.v);
    },
    scrollTrigger: { trigger: el, start: "top 92%", once: true },
  });
}

export { gsap, ScrollTrigger };
