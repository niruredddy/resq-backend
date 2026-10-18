export default function RotatingEarth() {
  return (
    <div className="earth-stage" aria-hidden="true">
      <div className="earth-orbit earth-orbit-back" />
      <div className="earth-globe">
        <div className="earth-texture" />
        <div className="earth-shade" />
      </div>
      <div className="earth-orbit earth-orbit-front" />
    </div>
  );
}
