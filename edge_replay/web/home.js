"use strict";

// Native controls stay useful independently of decorative motion.
const formatTabs = Array.from(document.querySelectorAll('[role="tab"]'));
function activateFormat(index, focus = false) {
  formatTabs.forEach((tab, tabIndex) => {
    const active = index === tabIndex;
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
    document.getElementById(tab.getAttribute("aria-controls")).hidden = !active;
    if (active && focus) tab.focus();
  });
}
formatTabs.forEach((tab, index) => {
  tab.addEventListener("click", () => activateFormat(index));
  tab.addEventListener("keydown", (event) => {
    let next;
    if (event.key === "ArrowRight") next = (index + 1) % formatTabs.length;
    if (event.key === "ArrowLeft")
      next = (index + formatTabs.length - 1) % formatTabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = formatTabs.length - 1;
    if (next !== undefined) {
      event.preventDefault();
      activateFormat(next, true);
    }
  });
});
activateFormat(0);

// Lenis is the only scrolling engine. The two-dimensional product preview needs
// no WebGL; all content is complete before motion initializes.
(() => {
  if (!window.gsap || !window.ScrollTrigger || !window.Lenis) return;
  gsap.registerPlugin(ScrollTrigger);
  const media = gsap.matchMedia();
  media.add("(prefers-reduced-motion: no-preference)", () => {
    const lenis = new Lenis({
      duration: 0.85,
      syncTouch: false,
      anchors: true,
      prevent: (node) => Boolean(node.closest("pre")),
    });
    lenis.on("scroll", ScrollTrigger.update);
    const tick = (time) => lenis.raf(time * 1000);
    gsap.ticker.add(tick);
    const intro = gsap.timeline({ defaults: { ease: "power3.out" } });
    intro
      .from(".hero-word", { y: 20, stagger: 0.04, duration: 0.7 }, 0)
      .from(
        ".hero-aside, .hero-bottom",
        { y: 11, stagger: 0.07, duration: 0.6 },
        0.1,
      )
      .from(".product-stage", { y: 20, duration: 0.8 }, 0.15);
    const workflow = gsap.from(".workflow-steps > li", {
      y: 16,
      stagger: 0.08,
      duration: 0.6,
      ease: "power3.out",
      scrollTrigger: {
        trigger: ".workflow-steps",
        start: "top 92%",
        once: true,
      },
    });
    const refresh = () => {
      lenis.resize();
      ScrollTrigger.refresh();
    };
    const picture = document.querySelector(".product-image-link img");
    if (picture.complete) refresh();
    else picture.addEventListener("load", refresh, { once: true });
    document.fonts.ready.then(refresh);
    const visibility = () => {
      if (document.hidden) lenis.stop();
      else lenis.start();
    };
    document.addEventListener("visibilitychange", visibility);
    return () => {
      intro.revert();
      workflow.revert();
      picture.removeEventListener("load", refresh);
      document.removeEventListener("visibilitychange", visibility);
      gsap.ticker.remove(tick);
      lenis.destroy();
    };
  });
  window.addEventListener("pagehide", () => media.revert(), { once: true });
})();
