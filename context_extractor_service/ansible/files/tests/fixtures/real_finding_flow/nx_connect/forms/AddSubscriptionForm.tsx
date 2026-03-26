import { useForm, SubmitHandler } from 'react-hook-form';
import Title from '@/app/components/ui/Title/Title';

type FormValues = { system: string; companyName: string };

const initialValues = { system: '', companyName: '' };

export default function AddSubscriptionForm() {
	const { watch } = useForm<FormValues>({ defaultValues: initialValues });
	const watchSystem = watch('system');
	const watchCompanyName = watch('companyName');
	const onSubmit: SubmitHandler<FormValues> = (data) => console.log(data);
	return `${watchSystem}:${watchCompanyName}:${onSubmit}:${Title}`;
}
