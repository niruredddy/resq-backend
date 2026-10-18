import { Lightning } from '@phosphor-icons/react';

export default function IntroSplash({ onComplete }) {
  return (
    <div className="intro-splash" role="dialog" aria-label="ResQ disaster response">
      <div className="intro-orbit intro-orbit-outer" aria-hidden="true" />
      <div className="intro-orbit intro-orbit-inner" aria-hidden="true" />
      <div className="intro-brand-mark" aria-hidden="true">
        <Lightning weight="fill" />
      </div>
      <div className="intro-wordmark">ResQ</div>
      <p className="intro-caption">Disaster response network</p>
      <div className="intro-progress" aria-hidden="true"><span /></div>
      <button className="intro-skip" onClick={onComplete} autoFocus>
        Skip intro
      </button>
    </div>
  );
}
