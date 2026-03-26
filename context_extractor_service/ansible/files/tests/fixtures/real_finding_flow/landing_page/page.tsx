import { trackPromoLinkClick } from '@/lib/logging/analytics';

export default function LandingPage() {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [showAlert, setShowAlert] = useState(true);
  const [alertState, setAlertState] = useState(1);
  const [showRedFov, setShowRedFov] = useState(false);
  const [showRect1, setShowRect1] = useState(false);

  useEffect(() => {
    const timers: NodeJS.Timeout[] = [];

    timers.push(setTimeout(() => setAlertState(2), 200));
    timers.push(setTimeout(() => setAlertState(3), 400));
    timers.push(setTimeout(() => setAlertState(4), 600));
    timers.push(setTimeout(() => setShowAlert(false), 1600));
    timers.push(setTimeout(() => setShowRedFov(true), 1600));
    timers.push(setTimeout(() => setShowRect1(true), 1850));
  }, []);
}
