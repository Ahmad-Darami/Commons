import { useThree } from '@react-three/fiber';
import { SparkRenderer, SplatMesh } from '@sparkjsdev/spark';
import { useEffect, useMemo, useState } from 'react';

/** Spark needs one SparkRenderer in the scene, or splats render black. */
export function SparkSetup() {
  const gl = useThree(s => s.gl);
  const spark = useMemo(() => new SparkRenderer({ renderer: gl }), [gl]);
  return <primitive object={spark} />;
}

/** The Room's photoreal Appearance. clean_scan.py writes it +y up, so no flip is needed. */
export function Appearance({ url, onReady }: { url: string; onReady?: (splats: number) => void }) {
  const mesh = useMemo(() => new SplatMesh({ url }), [url]);
  const [, setReady] = useState(false);
  useEffect(() => {
    let live = true;
    mesh.initialized.then(() => { if (live) { setReady(true); onReady?.(mesh.packedSplats?.numSplats ?? 0); } });
    return () => { live = false; mesh.dispose(); };
  }, [mesh, onReady]);
  return <primitive object={mesh} />;
}
