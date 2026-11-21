let coverAnimation;

window.mountCoverMotion = function (cover) {
  coverAnimation?.revert();
  if (!cover || !window.gsap || !window.ScrollTrigger) return;

  gsap.registerPlugin(ScrollTrigger);
  coverAnimation = gsap.matchMedia();
  coverAnimation.add(
    {
      motion: "(prefers-reduced-motion: no-preference)",
      compact: "(max-width: 800px)",
    },
    ({ conditions }) => {
      if (!conditions.motion) return;
      // Frontend Atlas's hero-frame scrub, using CSS sticky to avoid a pin spacer.
      const frame = cover.querySelector(".cover-frame");
      const photo = cover.querySelector(".cover-photo");
      const title = cover.querySelector(".cover-copy");
      const ending = conditions.compact
        ? "inset(4% 5% 6% 5% round 5px)"
        : "inset(7% 12% 8% 12% round 6px)";
      gsap
        .timeline({
          defaults: { ease: "none" },
          scrollTrigger: {
            trigger: cover,
            start: () => "top " + getComputedStyle(frame).top,
            end: () =>
              "+=" + Math.max(1, cover.offsetHeight - frame.offsetHeight),
            scrub: 0.6,
          },
        })
        .fromTo(
          frame,
          { clipPath: "inset(0% 0% 0% 0% round 0px)" },
          { clipPath: ending },
          0,
        )
        .fromTo(photo, { scale: 1.14 }, { scale: 1 }, 0)
        .to(title, { yPercent: -12 }, 0);

      const cards = document.querySelectorAll(".workflow-step");
      gsap.fromTo(
        cards,
        { y: 22, opacity: 0.62 },
        {
          y: 0,
          opacity: 1,
          stagger: 0.09,
          duration: 0.7,
          ease: "power3.out",
          scrollTrigger: { trigger: ".workflow", start: "top 86%", once: true },
        },
      );
    },
  );
};
