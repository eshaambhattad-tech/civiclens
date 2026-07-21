"use client";

import { useRef, useEffect } from "react";
import gsap from "gsap";

export default function AnimatedHero() {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const subtextRef = useRef<HTMLParagraphElement>(null);
  const statsRef = useRef<HTMLDivElement>(null);
  const dividerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const tl = gsap.timeline({ defaults: { ease: "power3.out" } });

    tl.fromTo(
      headingRef.current,
      { y: 50, opacity: 0, filter: "blur(8px)" },
      { y: 0, opacity: 1, filter: "blur(0px)", duration: 1 }
    )
      .fromTo(
        subtextRef.current,
        { y: 30, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.7 },
        "-=0.5"
      )
      .fromTo(
        dividerRef.current,
        { scaleX: 0 },
        { scaleX: 1, duration: 0.6, ease: "power2.inOut" },
        "-=0.3"
      )
      .fromTo(
        statsRef.current?.children
          ? Array.from(statsRef.current.children)
          : [],
        { y: 25, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.5, stagger: 0.12 },
        "-=0.2"
      );
  }, []);

  return (
    <div>
      <h1
        ref={headingRef}
        className="text-4xl sm:text-5xl lg:text-6xl font-bold mb-4 leading-tight opacity-0"
      >
        Who governs your corner
        <br />
        <span className="text-accent">of Cook County?</span>
      </h1>
      <p
        ref={subtextRef}
        className="text-muted text-lg sm:text-xl max-w-2xl mx-auto mb-8 opacity-0"
      >
        Enter any address to see every layer of local government — who
        represents you, where the money goes, and what&apos;s on the next
        agenda.
      </p>

      <div
        ref={dividerRef}
        className="h-px bg-border max-w-xs mx-auto mb-10 origin-center"
        style={{ transform: "scaleX(0)" }}
      />

      <div
        ref={statsRef}
        className="grid grid-cols-3 gap-8 max-w-md mx-auto text-center"
      >
        <div className="opacity-0">
          <div className="text-3xl sm:text-4xl font-bold text-foreground mb-1">
            178
          </div>
          <div className="text-xs sm:text-sm text-muted uppercase tracking-wide">
            Gov Units
          </div>
        </div>
        <div className="opacity-0">
          <div className="text-3xl sm:text-4xl font-bold text-foreground mb-1">
            225
          </div>
          <div className="text-xs sm:text-sm text-muted uppercase tracking-wide">
            Officials
          </div>
        </div>
        <div className="opacity-0">
          <div className="text-3xl sm:text-4xl font-bold text-foreground mb-1">
            342
          </div>
          <div className="text-xs sm:text-sm text-muted uppercase tracking-wide">
            Meetings
          </div>
        </div>
      </div>
    </div>
  );
}
