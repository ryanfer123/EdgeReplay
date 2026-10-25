"use strict";
// One scrolling engine: Lenis preserves the document flow of this workbench.
(() => {
  if (!window.gsap || !window.ScrollTrigger || !window.Lenis) return;
  gsap.registerPlugin(ScrollTrigger);
  const media = gsap.matchMedia();
  media.add("(prefers-reduced-motion: no-preference)", () => {
    const lenis = new Lenis({
      duration: 0.7,
      syncTouch: false,
      prevent: (node) => Boolean(node.closest("dialog,.table-wrap")),
    });
    lenis.on("scroll", ScrollTrigger.update);
    const ticker = (time) => lenis.raf(time * 1000);
    gsap.ticker.add(ticker);
    const intro = gsap.timeline({ defaults: { ease: "power3.out" } });
    intro
      .from(".word", { y: 17, stagger: 0.045, duration: 0.65 }, 0)
      .from(".hero-note", { y: 10, duration: 0.55 }, 0.1);
    const chart = () => {
      gsap.killTweensOf(".wave");
      gsap.from(".wave", {
        strokeDasharray: "2200 2200",
        strokeDashoffset: 2200,
        duration: 0.85,
        ease: "power2.out",
        clearProps: "strokeDasharray,strokeDashoffset",
      });
      lenis.resize();
      ScrollTrigger.refresh();
    };
    const visibility = () => {
      if (document.hidden) lenis.stop();
      else lenis.start();
    };
    document.addEventListener("edge:chart", chart);
    document.addEventListener("visibilitychange", visibility);
    document.fonts.ready.then(() => ScrollTrigger.refresh());
    return () => {
      intro.revert();
      gsap.killTweensOf(".wave");
      document.removeEventListener("edge:chart", chart);
      document.removeEventListener("visibilitychange", visibility);
      gsap.ticker.remove(ticker);
      lenis.destroy();
    };
  });
  window.addEventListener("pagehide", () => media.revert(), { once: true });
})();
