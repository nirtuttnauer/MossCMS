import {expect,test} from 'vitest'
import {deliveryShape,hiddenFieldCount,initialData,shapeSignature} from './fields'
import type {Field} from './api'
const fields:Field[]=[{name:'title',type:'text',localized:true},{name:'tags',type:'list',item:{name:'',type:'enum',options:['One','Two']}},{name:'group',type:'object',fields:[{name:'private',type:'text',private:true},{name:'image',type:'asset'}]},{name:'author',type:'reference'},{name:'when',type:'date'}]
test('initial values preserve nested and localized defaults without sharing mutable values', () => {
  const schema: Field[] = [...fields, { name: 'enabled', type: 'boolean' }, { name: 'translatedFlag', type: 'boolean', localized: true }, { name: 'translatedList', type: 'list', localized: true }]
  const values = initialData(schema)
  expect(values).toEqual({ title: { en: null }, tags: [], group: { private: null, image: null }, author: null, when: null, enabled: false, translatedFlag: { en: false }, translatedList: { en: [] } })
  ;(values.tags as unknown[]).push('changed')
  ;(values.group as Record<string, unknown>).image = 'changed'
  expect(initialData(schema).tags).toEqual([])
  expect(initialData(schema).group).toEqual({ private: null, image: null })
})
test('delivery signatures match nullable generated backend names and locale arguments',()=>{
 const shape=deliveryShape('Sample','sample',fields)
 expect(shape).toContain('tags(locale: String! = "en"): [CmsSampleTagsItemEnum]')
 expect(shape).toContain('title(locale: String! = "en"): String')
 expect(shape).toContain('image(locale: String! = "en"): AssetNode')
 expect(shape).toContain('author(locale: String! = "en"): ReferenceNode')
 expect(shape).toContain('when(locale: String! = "en"): Date')
 expect(shape).toContain('id: ID!');expect(shape).not.toContain('private(')
 expect(hiddenFieldCount(fields)).toBe(1)
 expect(shapeSignature(fields)).toBe(shapeSignature(fields.map(f=>({...f,label:'Changed',required:true,private:true}))))
})

test('migration diff never infers renames and only suggests explicit destructive changes',async()=>{
 const {fieldDiff,migrationSuggestion}=await import('./fields')
 const before:Field[]=[{name:'old',type:'text'},{name:'same',type:'text'}],after:Field[]=[{name:'new',type:'text',required:true},{name:'same',type:'number'}]
 expect(fieldDiff(before,after).map(d=>d.kind)).toEqual(['removed','changed','added'])
 expect(migrationSuggestion(before,after)).toEqual({rename:{},drop:['old'],defaults:{new:null}})
 expect(migrationSuggestion(before,after,{old:'new'})).toEqual({rename:{old:'new'},drop:[],defaults:{}})
})

test('templates validate and field duplication creates an isolated unique schema field',async()=>{
 const {TYPE_TEMPLATES,validateSchema,duplicateField}=await import('./fields')
 for(const template of Object.values(TYPE_TEMPLATES))expect(validateSchema(template)).toEqual([])
 const original:Field={name:'group',type:'object',private:true,fields:[{name:'title',type:'text'}]}
 const copy=duplicateField(original,[original,{...original,name:'groupCopy'}])
 expect(copy.name).toBe('groupCopy2');expect(copy.private).toBe(true)
 copy.fields![0].name='changed';expect(original.fields![0].name).toBe('title')
})

test('uses the configured locale recursively for new object and localized object fields', () => {
  expect(initialData([{ name: 'group', type: 'object', fields: [{ name: 'title', type: 'text', localized: true }] }, { name: 'localizedGroup', type: 'object', localized: true, fields: [{ name: 'active', type: 'boolean' }] }], 'he')).toEqual({ group: { title: { he: null } }, localizedGroup: { he: { active: false } } })
})
