// frontend/src/components/PageLoadingBar.tsx
import { useEffect, useState } from 'react';
import { useProject } from '../context/ProjectContext';

export default function PageLoadingBar() {
    const { selectedProject } = useProject();
    const [visible, setVisible] = useState(false);
    const [width, setWidth] = useState(0);

    useEffect(() => {
        setVisible(true);
        setWidth(0);

        // Animate to near-100% quickly, then finish
        const ramp = requestAnimationFrame(() => setWidth(85));

        const finish = setTimeout(() => {
            setWidth(100);
            setTimeout(() => setVisible(false), 200);
        }, 500);

        return () => {
            cancelAnimationFrame(ramp);
            clearTimeout(finish);
        };
    }, [selectedProject?.id]); // re-run on project change

    if (!visible) return null;

    return (
        <div style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            zIndex: 9999,
            height: 2,
            background: 'transparent',
            pointerEvents: 'none',
        }}>
            <div style={{
                height: '100%',
                width: `${width}%`,
                background: 'linear-gradient(90deg, #6366F1, #8B5CF6)',
                borderRadius: '0 2px 2px 0',
                transition: width === 100 ? 'width 0.2s ease' : 'width 0.5s ease-out',
                boxShadow: '0 0 8px rgba(99,102,241,0.6)',
            }} />
        </div>
    );
}
